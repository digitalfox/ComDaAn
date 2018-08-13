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

from argparse import ArgumentParser
from datetime import datetime, timedelta
from gitparsing import GitParser, get_log_from_repositories
from bokeh.plotting import figure, show
from bokeh.models import HoverTool, LinearColorMapper
from bokeh.models.sources import ColumnDataSource
from bokeh.palettes import Magma256
from bokeh.io import output_file


if __name__ == "__main__":
    # Parse the args before all else
    arg_parser = ArgumentParser(description="A tool for visualizing, week by week, who contributes code",
                                parents=[GitParser.get_argument_parser()])
    arg_parser.add_argument("--palette", choices=["blue4", "magma256"], default="magma",
                            help="Choose a palette (default is magma256)")
    arg_parser.add_argument("-t", "--title",
                            help="Title")
    arg_parser.add_argument("-o", "--output",
                            help="Output file (default is 'result.html')")
    args = arg_parser.parse_args()

    start_date = args.start
    end_date = args.end
    output_filename = args.output or "result.html"

    log = get_log_from_repositories(args.paths, start_date, end_date)

    start_dates = log.groupby('author_name')['author_name', 'date'].min()
    authors = start_dates.sort_values(['date', 'author_name'], ascending=False).loc[:, 'author_name'].tolist()

    daily_activity = log.loc[:, ['author_name', 'date', 'id']].groupby(['author_name', 'date']).count()
    daily_activity.columns = ['count']

    weekly_activity = daily_activity.groupby('author_name').resample("W", level=1).sum()
    weekly_activity = weekly_activity.loc[lambda x: x['count'] > 0]
    weekly_activity = weekly_activity.reset_index(level=['author_name', 'date'])
    weekly_activity['date'] = weekly_activity['date'].apply(lambda x: x - timedelta(days=3))
    weekly_activity['week_name'] = weekly_activity['date'].apply(lambda x: "%s-%s" % x.isocalendar()[:2])

    palette = list(reversed(Magma256))
    color_mapper = LinearColorMapper(palette=palette,
                                     low=weekly_activity['count'].min(),
                                     high=weekly_activity['count'].max())
    if args.palette == "blue4":
        palette = ["#EAF5F9", "#D6EBF2", "#C1E2EC", "#ADD8E6"]
        color_mapper = LinearColorMapper(palette=palette, low=0, high=4)

    output_file(output_filename)
    p = figure(x_axis_type="datetime", y_range=authors,
               sizing_mode="stretch_both",
               active_scroll="wheel_zoom",
               title=args.title)
    p.add_tools(HoverTool(tooltips=[("Author", "@author_name"),
                                    ("Week", "@week_name"),
                                    ("Count", "@count")]))
    p.rect("date", "author_name",
           source=ColumnDataSource(weekly_activity),
           fill_color={'field': 'count', 'transform': color_mapper},
           line_color={'field': 'count', 'transform': color_mapper},
           width=1000 * 60 * 60 * 24 * 7,
           height=1)
    show(p)
