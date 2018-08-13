#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# Copyright 2018 Kevin Ottens <ervin@ipsquad.net>
#
# The authors license this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from multiprocessing.pool import Pool

import pandas as pd
import networkx as nx

from argparse import ArgumentParser
from gitparsing import GitParser, get_log_from_repositories
from bokeh.plotting import figure, show
from bokeh.models.graphs import from_networkx, NodesAndLinkedEdges
from bokeh.models import MultiLine, Circle, HoverTool, TapTool, BoxSelectTool, LinearColorMapper
from bokeh.models.sources import ColumnDataSource
from bokeh.palettes import Spectral4, Magma11
from bokeh.io import output_file
from itertools import combinations
from functools import reduce

if __name__ == "__main__":
    # Parse the args before all else
    arg_parser = ArgumentParser(description="A tool for showing who has worked with whom within repositories",
                                parents=[GitParser.get_argument_parser()])
    arg_parser.add_argument("-t", "--title",
                            help="Title")
    arg_parser.add_argument("-o", "--output",
                            help="Output file (default is 'result.html')")
    args = arg_parser.parse_args()

    start_date = args.start
    end_date = args.end
    output_filename = args.output or "result.html"

    log = get_log_from_repositories(args.paths, start_date, end_date)

    groups = log.loc[:, ['author_name', 'files']].groupby('author_name')
    files = groups.aggregate(lambda x: reduce(set.union, x))

    edges = list(combinations(files.index.tolist(), 2))
    edge_list = pd.DataFrame(edges, columns=['source', 'target'])
    edge_list['weight'] = edge_list.apply(lambda x: len(files.loc[x['source']]['files']
                                                             .intersection(files.loc[x['target']]['files'])),
                                          axis=1)

    graph = nx.convert_matrix.from_pandas_edgelist(edge_list, edge_attr=['weight'])
    no_edges = []
    for u, v, weight in graph.edges.data('weight'):
        if weight == 0:
            no_edges.append((u, v))

    graph.remove_edges_from(no_edges)

    degrees = nx.degree_centrality(graph)
    nodes = pd.DataFrame.from_records([degrees]).transpose()
    nodes.columns = ["centrality"]

    palette = list(reversed(Magma11))
    color_mapper = LinearColorMapper(palette=palette,
                                     low=nodes['centrality'].min(),
                                     high=nodes['centrality'].max())

    output_file(output_filename)
    p = figure(x_range=(-1.1, 1.1), y_range=(-1.1, 1.1),
               sizing_mode="stretch_both",
               active_scroll="wheel_zoom",
               title=args.title)

    p.add_tools(HoverTool(tooltips=[("Name", "@index"), ("Centrality", "@centrality")]), TapTool(), BoxSelectTool())

    p.xaxis.visible = False
    p.yaxis.visible = False
    p.grid.visible = False

    renderer = from_networkx(graph, nx.kamada_kawai_layout)

    renderer.node_renderer.data_source.add(nodes['centrality'], "centrality")
    renderer.node_renderer.glyph = Circle(size=15, fill_color={'field': 'centrality', 'transform': color_mapper})
    renderer.node_renderer.selection_glyph = Circle(size=15, fill_color=Spectral4[2])
    renderer.node_renderer.hover_glyph = Circle(size=15, fill_color=Spectral4[1])

    renderer.edge_renderer.glyph = MultiLine(line_color="#CCCCCC", line_alpha=0.8, line_width=2)
    renderer.edge_renderer.selection_glyph = MultiLine(line_color=Spectral4[2], line_width=4)
    renderer.edge_renderer.hover_glyph = MultiLine(line_color=Spectral4[1], line_width=4)

    renderer.selection_policy = NodesAndLinkedEdges()
    renderer.inspection_policy = NodesAndLinkedEdges()

    p.renderers.append(renderer)
    show(p)
