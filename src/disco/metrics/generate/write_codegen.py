from .types import *
from pathlib import Path
from typing import TextIO
import os
import re

def _write_metric(f: TextIO, metric: Metric, prefix: str):
    full_name = re.sub(r'(?<!^)(?=[A-Z])', '_', metric.name).upper()
    description = ' '.join([line.strip() for line in metric.description.split('\n')]).strip()
    converter = 'NONE'
    if isinstance(metric, HistogramMetric):
        converter = metric.converter.name

    if isinstance(metric, GaugeEnumMetric) or isinstance(metric, CounterEnumMetric):
        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_OFF  ({metric.offset}UL)\n')
        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_CNT  ({len(metric.enum.values)}UL)\n\n')

        offset: int = 0

        for value in metric.enum.values:
            value_name = re.sub(r'(?<!^)(?=[A-Z])', '_', value.name).upper()
            f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_{value_name.upper()}_OFF  ({metric.offset+offset}UL)\n')
            f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_{value_name.upper()}_NAME "{prefix}_{full_name.lower()}_{value_name.lower()}"\n')
            f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_{value_name.upper()}_TYPE (FD_METRICS_TYPE_{metric.type.name})\n')
            f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_{value_name.upper()}_DESC "{description} ({value.label})"\n')
            f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_{value_name.upper()}_CVT  (FD_METRICS_CONVERTER_{converter})\n\n')
            offset += 1
    else:
        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_OFF  ({metric.offset}UL)\n')
        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_NAME "{prefix}_{full_name.lower()}"\n')
        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_TYPE (FD_METRICS_TYPE_{metric.type.name})\n')
        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_DESC "{description}"\n')
        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_CVT  (FD_METRICS_CONVERTER_{converter})\n')

    if isinstance(metric, HistogramMetric):
        if metric.converter == HistogramConverter.SECONDS:
            min_str = str(float(metric.min))
            max_str = str(float(metric.max))
        else:
            min_str = str(int(metric.min)) + "UL"
            max_str = str(int(metric.max)) + "UL"

        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_MIN  ({min_str})\n')
        f.write(f'#define FD_METRICS_{metric.type.name.upper()}_{prefix.upper()}_{full_name}_MAX  ({max_str})\n')

    f.write('\n')

def _write_common(metrics: Metrics):
    with open(Path(__file__).parent / '../generated' / 'fd_metrics_all.h', 'w') as f:
        f.write('/* THIS FILE IS GENERATED BY gen_metrics.py. DO NOT HAND EDIT. */\n\n')
        f.write('#include "../fd_metrics_base.h"\n\n')
        for tile in metrics.tiles.keys():
            f.write(f'#include "fd_metrics_{tile.name.lower()}.h"\n')

        f.write('/* Start of LINK OUT metrics */\n\n')
        for metric in metrics.link_out:
            _write_metric(f, metric, "link")

        f.write('/* Start of LINK IN metrics */\n\n')
        for metric in metrics.link_in:
            _write_metric(f, metric, "link")

        f.write('/* Start of TILE metrics */\n\n')
        for metric in metrics.common:
            _write_metric(f, metric, "tile")

        offset = sum([int(metric.footprint()/8) for metric in metrics.common])
        f.write(f'\n#define FD_METRICS_ALL_TOTAL ({offset}UL)\n')
        f.write(f'extern const fd_metrics_meta_t FD_METRICS_ALL[FD_METRICS_ALL_TOTAL];\n')
        f.write(f'\n#define FD_METRICS_ALL_LINK_IN_TOTAL ({len(metrics.link_in)}UL)\n')
        f.write(f'extern const fd_metrics_meta_t FD_METRICS_ALL_LINK_IN[FD_METRICS_ALL_LINK_IN_TOTAL];\n')
        f.write(f'\n#define FD_METRICS_ALL_LINK_OUT_TOTAL ({len(metrics.link_out)}UL)\n')
        f.write(f'extern const fd_metrics_meta_t FD_METRICS_ALL_LINK_OUT[FD_METRICS_ALL_LINK_OUT_TOTAL];\n')

        # Max size of any particular tiles metrics
        max_offset = 0
        for (tile, tile_metrics) in metrics.tiles.items():
            tile_offset = sum([int(metric.footprint() / 8) for metric in tile_metrics])
            if tile_offset > max_offset:
                max_offset = tile_offset

        # Kind of a hack for now.  Different tiles should get a different size.
        f.write(f'\n#define FD_METRICS_TOTAL_SZ (8UL*{max_offset+offset}UL)\n')
        f.write(f'\n#define FD_METRICS_TILE_KIND_CNT {len(metrics.tiles)}\n')
        f.write(f'extern const char * FD_METRICS_TILE_KIND_NAMES[FD_METRICS_TILE_KIND_CNT];\n')
        f.write(f'extern const ulong FD_METRICS_TILE_KIND_SIZES[FD_METRICS_TILE_KIND_CNT];\n')
        f.write(f'extern const fd_metrics_meta_t * FD_METRICS_TILE_KIND_METRICS[FD_METRICS_TILE_KIND_CNT];\n')

    with open(Path(__file__).parent / '../generated' / 'fd_metrics_all.c', 'w') as f:
        f.write('/* THIS FILE IS GENERATED BY gen_metrics.py. DO NOT HAND EDIT. */\n')
        f.write('#include "fd_metrics_all.h"\n\n')

        f.write('const fd_metrics_meta_t FD_METRICS_ALL[FD_METRICS_ALL_TOTAL] = {\n')
        for metric in metrics.common:
            declare: str = ''
            if metric.type == MetricType.COUNTER:
                declare = 'DECLARE_METRIC_COUNTER'
            elif metric.type == MetricType.GAUGE:
                declare = 'DECLARE_METRIC_GAUGE'
            elif metric.type == MetricType.HISTOGRAM:
                assert isinstance(metric, HistogramMetric)
                if metric.converter == HistogramConverter.SECONDS:
                    declare = 'DECLARE_METRIC_HISTOGRAM_SECONDS'
                elif metric.converter == HistogramConverter.NONE:
                    declare = 'DECLARE_METRIC_HISTOGRAM_NONE'
                else:
                    raise Exception(f'Unknown histogram converter: {metric.converter}')

            full_name = re.sub(r'(?<!^)(?=[A-Z])', '_', metric.name).upper()
            if isinstance(metric, GaugeEnumMetric) or isinstance(metric, CounterEnumMetric):
                for value in metric.enum.values:
                    value_name = re.sub(r'(?<!^)(?=[A-Z])', '_', value.name).upper()
                    f.write(f'    {declare}( TILE, {full_name}_{value_name} ),\n')
            else:
                f.write(f'    {declare}( TILE, {full_name} ),\n')
        f.write('};\n\n')

        f.write('const fd_metrics_meta_t FD_METRICS_ALL_LINK_IN[FD_METRICS_ALL_LINK_IN_TOTAL] = {\n')
        for metric in metrics.link_in:
            declare: str = ''
            if metric.type == MetricType.COUNTER:
                declare = 'DECLARE_METRIC_COUNTER'
            elif metric.type == MetricType.GAUGE:
                declare = 'DECLARE_METRIC_GAUGE'
            elif metric.type == MetricType.HISTOGRAM:
                assert isinstance(metric, HistogramMetric)
                if metric.converter == HistogramConverter.SECONDS:
                    declare = 'DECLARE_METRIC_HISTOGRAM_SECONDS'
                elif metric.converter == HistogramConverter.NONE:
                    declare = 'DECLARE_METRIC_HISTOGRAM_NONE'
                else:
                    raise Exception(f'Unknown histogram converter: {metric.converter}')

            full_name = re.sub(r'(?<!^)(?=[A-Z])', '_', metric.name).upper()
            if isinstance(metric, GaugeEnumMetric) or isinstance(metric, CounterEnumMetric):
                for value in metric.enum.values:
                    value_name = re.sub(r'(?<!^)(?=[A-Z])', '_', value.name).upper()
                    f.write(f'    {declare}( LINK, {full_name}_{value_name} ),\n')
            else:
                f.write(f'    {declare}( LINK, {full_name} ),\n')
        f.write('};\n\n')

        f.write(f'const fd_metrics_meta_t FD_METRICS_ALL_LINK_OUT[FD_METRICS_ALL_LINK_OUT_TOTAL] = {{\n')
        for metric in metrics.link_out:
            declare: str = ''
            if metric.type == MetricType.COUNTER:
                declare = 'DECLARE_METRIC_COUNTER'
            elif metric.type == MetricType.GAUGE:
                declare = 'DECLARE_METRIC_GAUGE'
            elif metric.type == MetricType.HISTOGRAM:
                assert isinstance(metric, HistogramMetric)
                if metric.converter == HistogramConverter.SECONDS:
                    declare = 'DECLARE_METRIC_HISTOGRAM_SECONDS'
                elif metric.converter == HistogramConverter.NONE:
                    declare = 'DECLARE_METRIC_HISTOGRAM_NONE'
                else:
                    raise Exception(f'Unknown histogram converter: {metric.converter}')

            full_name = re.sub(r'(?<!^)(?=[A-Z])', '_', metric.name).upper()
            if isinstance(metric, GaugeEnumMetric) or isinstance(metric, CounterEnumMetric):
                for value in metric.enum.values:
                    value_name = re.sub(r'(?<!^)(?=[A-Z])', '_', value.name).upper()
                    f.write(f'    {declare}( LINK, {full_name}_{value_name} ),\n')
            else:
                f.write(f'    {declare}( LINK, {full_name} ),\n')
        f.write('};\n\n')

        f.write(f'const char * FD_METRICS_TILE_KIND_NAMES[FD_METRICS_TILE_KIND_CNT] = {{\n')
        for tile in Tile:
            if tile in metrics.tiles:
                f.write(f'    "{tile.name.lower()}",\n')
        f.write('};\n\n')

        f.write(f'const ulong FD_METRICS_TILE_KIND_SIZES[FD_METRICS_TILE_KIND_CNT] = {{\n')
        for tile in Tile:
            if tile in metrics.tiles:
                f.write(f'    FD_METRICS_{tile.name}_TOTAL,\n')
        f.write('};\n')

        f.write(f'const fd_metrics_meta_t * FD_METRICS_TILE_KIND_METRICS[FD_METRICS_TILE_KIND_CNT] = {{\n')
        for tile in Tile:
            if tile in metrics.tiles:
                f.write(f'    FD_METRICS_{tile.name},\n')
        f.write('};\n')


def _write_tile(tile: Tile, metrics: List[Metric]):
    with open(Path(__file__).parent / '../generated' / f'fd_metrics_{tile.name.lower()}.h', 'w') as f:
        f.write('/* THIS FILE IS GENERATED BY gen_metrics.py. DO NOT HAND EDIT. */\n\n')
        f.write('#include "../fd_metrics_base.h"\n\n')

        for metric in metrics:
            _write_metric(f, metric, tile.name.lower())

        total = sum([int(metric.count()) for metric in metrics])
        f.write(f'#define FD_METRICS_{tile.name}_TOTAL ({total}UL)\n')
        f.write(f'extern const fd_metrics_meta_t FD_METRICS_{tile.name}[FD_METRICS_{tile.name}_TOTAL];\n')

    with open(Path(__file__).parent / '../generated' / f'fd_metrics_{tile.name.lower()}.c', 'w') as f:
        f.write('/* THIS FILE IS GENERATED BY gen_metrics.py. DO NOT HAND EDIT. */\n')
        f.write(f'#include "fd_metrics_{tile.name.lower()}.h"\n\n')

        f.write(f'const fd_metrics_meta_t FD_METRICS_{tile.name}[FD_METRICS_{tile.name}_TOTAL] = {{\n')
        for metric in metrics:
            declare: str = ''
            if metric.type == MetricType.COUNTER:
                declare = 'DECLARE_METRIC_COUNTER'
            elif metric.type == MetricType.GAUGE:
                declare = 'DECLARE_METRIC_GAUGE'
            elif metric.type == MetricType.HISTOGRAM:
                assert isinstance(metric, HistogramMetric)
                if metric.converter == HistogramConverter.SECONDS:
                    declare = 'DECLARE_METRIC_HISTOGRAM_SECONDS'
                elif metric.converter == HistogramConverter.NONE:
                    declare = 'DECLARE_METRIC_HISTOGRAM_NONE'
                else:
                    raise Exception(f'Unknown histogram converter: {metric.converter}')

            full_name = re.sub(r'(?<!^)(?=[A-Z])', '_', metric.name).upper()
            if isinstance(metric, GaugeEnumMetric) or isinstance(metric, CounterEnumMetric):
                for value in metric.enum.values:
                    value_name = re.sub(r'(?<!^)(?=[A-Z])', '_', value.name).upper()
                    f.write(f'    {declare}( {tile.name}, {full_name}_{value_name} ),\n')
            else:
                f.write(f'    {declare}( {tile.name}, {full_name} ),\n')
        f.write('};\n')

def write_codegen(metrics: Metrics):
    os.makedirs(Path(__file__).parent / '../generated', exist_ok=True)

    _write_common(metrics)
    for (tile, tile_metrics) in metrics.tiles.items():
        _write_tile(tile, tile_metrics)


    print(f'Generated {metrics.count()} metrics for {len(metrics.tiles)} tiles')
