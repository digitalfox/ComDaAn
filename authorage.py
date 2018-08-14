#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# Copyright 2018 Sebastien Renard <sebastien.renard@digitalfox.org>
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
from datetime import timedelta
from gitparsing import GitParser, get_log_from_repositories

from pandas import DataFrame, DatetimeIndex
from bokeh.plotting import figure, show
from bokeh.models import HoverTool, LinearAxis, Range1d
from bokeh.models.annotations import Legend
from bokeh.models.sources import ColumnDataSource
from bokeh.palettes import Category10
from bokeh.io import output_file


if __name__ == "__main__":
    # Parse the args before all else
    arg_parser = ArgumentParser(description="A tool for visualizing, month by month the age of contributors",
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
    log["date"] = DatetimeIndex(log['date']).to_period("W").to_timestamp()
    log["date"] = log['date'].apply(lambda x: x - timedelta(days=3))

    log_by_author = log.groupby("author_name")
    authors_age = DataFrame()
    authors_age["min"] = log_by_author["date"].min()
    authors_age["max"] = log_by_author["date"].max()
    authors_age["month_arrival"] = log_by_author["date"].min()
    authors_age["month_departure"] = log_by_author["date"].max()
    authors_age["author_name"] = authors_age.index

    # Compute age of author for each commit
    log["age"] = log.apply(lambda x: (x["date"] - authors_age["min"][x["author_name"]]).days/365, axis=1)

    log_by_date = log.groupby("date")

    # Gather data for ploting
    data = DataFrame()
    data["commit_author_age"] = log_by_date["age"].sum() / log_by_date["id"].count()
    data["commit_count"] = log_by_date["id"].count()
    data["newcomers_count"] = authors_age.groupby("month_arrival")["author_name"].count()
    data["leaving_count"] = authors_age.groupby("month_departure")["author_name"].count()
    data["cumulative_newcomers"] = data.newcomers_count.cumsum()
    data["cumulative_leaving"] = data.leaving_count.cumsum()
    data["active_count"] = data["cumulative_newcomers"] - data["cumulative_leaving"]

    smoothed = data.rolling(30, center=True, win_type="triang").mean()
    data["commit_author_age_smooth"] = smoothed["commit_author_age"]
    data["commit_count_smooth"] = smoothed["commit_count"]

    output_file(output_filename)
    p = figure(x_axis_type="datetime",
               sizing_mode="stretch_both",
               active_scroll="wheel_zoom",
               title=args.title,
               y_range=Range1d(start=0, end=data["commit_author_age"].max()))
    p.xaxis.axis_label = "Date"
    p.yaxis.axis_label = "Commit author age"

    p.extra_y_ranges = {'commit_count_range': Range1d(start=0, end=max(data['commit_count'].max(), data["active_count"].max()))}
    p.add_layout(LinearAxis(y_range_name="commit_count_range", axis_label="Number of commit / active dev"), "right")

    p.add_layout(Legend(), "below")

    p.add_tools(HoverTool(tooltips=[("Date", "@date{%Y-w%V}"),
                                    ("Commit author age", "@commit_author_age"),
                                    ("Number of commit", "@commit_count"),
                                    ("Number of active dev", "@active_count")],
                          formatters={'date': 'datetime'},
                          point_policy='snap_to_data'))

    p.circle("date", "commit_author_age", source=ColumnDataSource(data),
             color=Category10[3][0], fill_alpha=0.1, line_alpha=0.2)

    p.line("date", "commit_author_age_smooth", source=ColumnDataSource(data),
           line_width=2, color=Category10[3][0], legend="Commit Author average age (years)")

    p.line("date", "commit_count_smooth", source=ColumnDataSource(data),
           line_width=2, color=Category10[3][1], legend="Number of commit", y_range_name="commit_count_range")

    p.line("date", "active_count", source=ColumnDataSource(data.dropna()),
           line_width=2, color=Category10[3][2], legend="Active developpers", y_range_name="commit_count_range")

    show(p)
