#!/usr/bin/env python3
# -*- coding: utf-8 -*
#
# Copyright 2017 Paul Adams <paul@baggerspion.net>
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

from datetime import datetime
from multiprocessing.pool import Pool

from pytz import utc

import os
import pandas
import subprocess
import importlib
import glob
import argparse

GIT_COMMIT_FIELDS = ['id', 'author_name', 'author_email', 'date', 'message', 'files']
GIT_LOG_FORMAT = ["%H", "%an", "%ae", "%ad", "%s"]
GIT_LOG_FORMAT = "%x1e" + "%x1f".join(GIT_LOG_FORMAT) + "%x1f"


class GitParser:
    def __init__(self):
        self.__paths = []
        self.__rulesets = []

        rulesets_dir = os.path.dirname(__file__) + "/rulesets"
        for file in glob.glob(rulesets_dir + "/*.py"):
            module_name = os.path.splitext(os.path.basename(file))[0]
            module = importlib.import_module("rulesets.%s" % (module_name))
            self.__rulesets.append(module)

    @staticmethod
    def get_argument_parser() -> argparse.ArgumentParser:
        arg_parser = argparse.ArgumentParser(add_help=False)
        arg_parser.add_argument("paths", metavar="path", nargs="+",
                                help="Path of a git repository to process or of a directory containing git repositories")
        arg_parser.add_argument("-f", "--start",
                                help="Start date")
        arg_parser.add_argument("-u", "--end",
                                help="End date")
        return arg_parser

    def add_repository(self, path):
        if not isinstance(path, str):
            raise ValueError("String expected")

        abs_path = os.path.abspath(os.path.expanduser(path))
        git_path = os.path.join(abs_path, ".git")
        if not os.path.exists(git_path):
            raise ValueError("Git repository expected, no %s found" % git_path)

        self.__paths.append(abs_path)

    def add_repositories(self, paths):
        if isinstance(paths, str):
            self.__add_repositories([paths])
        else:
            self.__add_repositories(paths)

    def __add_repositories(self, paths):
        for path in paths:
            abs_path = os.path.abspath(os.path.expanduser(path))
            git_path = os.path.join(abs_path, ".git")

            if os.path.exists(git_path):
                self.add_repository(abs_path)
            elif os.path.isdir(abs_path):
                subpaths = list(map(lambda x: os.path.join(abs_path, x), os.listdir(abs_path)))
                for subpath in subpaths:
                    self.add_repositories(subpath)

    def get_log(self, start_date=None, end_date=None):
        entries = []
        for path in self.__paths:
            entries.extend(self.__create_log_entries(path, start_date, end_date))

        log = pandas.DataFrame(entries, columns=GIT_COMMIT_FIELDS + ['repository'])
        log['files'] = log['files'].apply(lambda x: set(x))
        log['date'] = log['date'].apply(lambda x: datetime(year=x.year, month=x.month, day=x.day))
        return log

    def __create_log_entries(self, path, start_date=None, end_date=None):
        command = "git --git-dir %s/.git log" % (path)
        command += " --date-order --reverse --all --date=iso --name-only"
        command += " --pretty=format:%s" % (GIT_LOG_FORMAT)

        if start_date:
            command += " --since %s" % (start_date)

        if end_date:
            command += " --until %s" % (end_date)

        log = self.__run_command(command)

        # Process the log into a list
        log = log.strip("\n\x1e").split("\x1e")
        log = [row.strip().split("\x1f") for row in log]
        log = [dict(zip(GIT_COMMIT_FIELDS, row)) for row in log]

        # Filter the log
        start_datetime = None
        if start_date:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")

        end_datetime = None
        if end_date:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")

        log = list(filter(lambda x: self.__is_entry_acceptable(x, start_datetime, end_datetime), log))
        log = list(map(lambda x: self.__postprocess_entry(os.path.basename(path), x), log))

        return log

    def __run_command(self, command):
        process = subprocess.Popen(command.split(" "),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   universal_newlines=False)
        (log, err) = process.communicate()

        if process.returncode != 0:
            raise OSError(log)

        return log.decode("utf-8", errors="replace")

    def __is_entry_acceptable(self, entry, start_datetime, end_datetime):
        for ruleset in self.__rulesets:
            if not ruleset.is_entry_acceptable(entry):
                return False

        try:
            entry_datetime = datetime.strptime(entry['date'], "%Y-%m-%d %H:%M:%S %z")
            entry_datetime = entry_datetime.astimezone(utc)

            # Sometimes git gives us entries from the wrong date range
            if start_datetime and entry_datetime.date() < start_datetime.date():
                return False

            if end_datetime and entry_datetime.date() > end_datetime.date():
                return False

            if entry_datetime.date() > datetime.now().date():
                return False

        except KeyError:
            return False

        return True

    def __postprocess_entry(self, repository, entry):
        try:
            files = entry['files'].strip("\n")
            files = files.split("\n")
            files = list(map(lambda x: "%s:%s" % (repository, x), files))
            entry['files'] = files
        except KeyError:
            entry['files'] = []

        entry['repository'] = repository
        entry['id'] = "%s:%s" % (repository, entry['id'])
        entry['date'] = datetime.strptime(entry['date'], "%Y-%m-%d %H:%M:%S %z")
        entry['date'] = entry['date'].astimezone(utc)

        for ruleset in self.__rulesets:
            ruleset.postprocess_entry(entry)

        return entry


def get_log_from_repository(path, start_date, end_date):
    """Simple wrapper function around gitparser to ease calling it in parralel
    @:param path: path to git repository
    @:param start_date
    @:param end_date
    @:return structured log data as a pandas dataframe
    """
    parser = GitParser()
    parser.add_repositories(path)
    log = parser.get_log(start_date, end_date)
    return log


def get_log_from_repositories(paths, start_date, end_date):
    """Parralel version of get_log_from_repository
        @:param path: path to git repository
        @:param start_date
        @:param end_date
        @:return structured log data as a pandas dataframe
        """
    with Pool() as pool: # use a pool with a many workers as cpu availables on this host
        results = [pool.apply_async(get_log_from_repository, args=(path, start_date, end_date)) for path in paths]
        log = pandas.concat([p.get() for p in results])  # Concatenate results in single pandas dataframe

    return log