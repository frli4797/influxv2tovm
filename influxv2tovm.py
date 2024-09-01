#!/usr/bin/env python3
"""
 @author Fredrik Lilja

 SPDX-License-Identifier: Apache-2.0
"""
import datetime
import logging
import os
import warnings
from typing import Iterable, Dict, List

import humanize
import pandas as pd
import requests
from influxdb_client import InfluxDBClient, QueryApi
from influxdb_client.client.warnings import MissingPivotFunction

warnings.simplefilter("ignore", MissingPivotFunction)

# Create a custom logger
logger = logging.getLogger(__name__)
# noinspection SpellCheckingInspection
logging.basicConfig(filename="migrator.log", encoding="utf-8", level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s -  %(message)s')

try:
    # noinspection PyUnresolvedReferences
    import dotenv

    dotenv.load_dotenv(dotenv_path=".env")
except ImportError as err:
    pass


class Stats:
    bytes: int = 0
    lines: int = 0

    def humanized_bytes(self) -> str:
        """
        Get the number of bytes as natural size.
        :return: str
        """
        return humanize.naturalsize(self.bytes)

    def increment(self, lines: str):
        """
        Increments the number of bytes and the number of lines from a string.
        :param lines: lines string
        """
        no_lines = lines.count('\n')
        self.lines = self.lines + no_lines

        new_bytes = len(lines.encode("utf8"))
        self.bytes += new_bytes


class InfluxMigrator:
    __query_api: QueryApi
    __measurement_key = "_measurement"
    __client: InfluxDBClient

    # noinspection SpellCheckingInspection
    def __init__(self, bucket: str, vm_url: str, chunksize: int = 100, dry_run: bool = False, pivot: bool = False):
        self.bucket = bucket
        self.vm_url: str = vm_url
        self.chunksize = chunksize
        # now_datetime_str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        # self.__progress_file = open(f".migrator_{now_datetime_str}", 'w')
        self.stats = Stats()
        self.dry_run = dry_run
        self.pivot = pivot
        if pivot:
            self.__measurement_key = "entity_id"
        else:
            self.__measurement_key = "_measurement"

    def __del__(self):
        self.__client.close()

    def influx_connect(self):
        """
        Connects to the influx database.
        """
        self.__client = InfluxDBClient.from_env_properties()
        self.__query_api = self.__client.query_api()

    def migrate(self):

        if self.__query_api is None:
            raise AssertionError("No connection to InfluxDb started.")

        # Get all unique series by reading first entry of every table.
        # With latest InfluxDB we could possibly use "schema.measurements()" but this doesn't exist in 2.0
        measurements_and_fields = self.__find_all_measurements()

        field_no = 1
        for meas in measurements_and_fields:
            no_lines = 0

            chunk_query = f"""
                        from(bucket: "{self.bucket}")
                        |> range(start: -100d, stop: now())
                        |> filter(fn: (r) => r["{self.__measurement_key}"] == "{meas}")
                        |> limit(n: {self.chunksize}, offset: _offset)
                        """
            df_empty = False
            offset = 0
            while not df_empty:
                params = {"_offset": offset}
                result = self.__query_api.query_data_frame(chunk_query, params=params)
                if type(result) is not list:
                    result: list = [result]
                else:
                    print("")

                for df in result:
                    df_empty = df.empty
                    if df_empty:
                        break

                    # Increase offset with the number of rows in the DataFrame.
                    offset += df.shape[0]

                    assert (type(df) is pd.DataFrame)
                    lines_protocol_str = self.__get_influxdb_lines(df)
                    self.stats.increment(lines_protocol_str)
                    no_lines += lines_protocol_str.count('\n') + 1

                    if not self.dry_run:
                        requests.post(
                            f"{self.vm_url}/write?db={self.bucket}", data=lines_protocol_str.encode("utf8"))
                    else:
                        print(lines_protocol_str)

                    print(
                        f"Wrote {no_lines} lines "
                        f"bytes to VictoriaMetrics db={self.bucket} for {meas}. "
                        f"Total: {self.stats.humanized_bytes()} "
                        f"({field_no}/{len(measurements_and_fields)})",
                        end='\r')
            field_no += 1

    @staticmethod
    def __whitelist_measurements(measurements_and_fields: List) -> List[tuple]:
        """
        Applies a whitelist to the list of measurements and fields. Does nothing if no whitelist is found.

        :param measurements_and_fields :
        :return:  the new measurements and fields tuple list with the whitelist applied.
        """
        whitelist: List[tuple] = []
        whitelist_path = "whitelist.txt"
        if os.path.exists(whitelist_path):
            try:
                with open(whitelist_path, 'r') as f:
                    whitelist_rows = f.read().splitlines()

                    for row_str in whitelist_rows:
                        row = row_str.split(' ')
                        if len(row) > 3:
                            tup: tuple = row[1], row[2]
                            whitelist.append(tup)
            except OSError:
                print("Problem reading whitelist. Skipping")

            if len(whitelist) > 0:
                m_a_f_set = set(measurements_and_fields)
                whitelist_set = set(whitelist)
                measurements_and_fields = list(set.intersection(m_a_f_set, whitelist_set))

        return measurements_and_fields

    def __find_all_measurements(self):
        """
        Finds all permutations of measurements and fields.
        :return: a list of tuples
        """

        print("Finding unique time series.")
        first_in_series = f"""
           from(bucket: "{self.bucket}")
           |> range(start: 0, stop: now())
           |> first()"""
        timeseries: List[pd.DataFrame] = self.__query_api.query_data_frame(first_in_series)

        measurements_and_fields = set()
        for df in timeseries:
            measurements_and_fields.update(df[self.__measurement_key].unique())

        print(f"Found {len(measurements_and_fields)} unique time series")
        return measurements_and_fields

    @staticmethod
    def __get_tag_cols(dataframe_keys: Iterable) -> Iterable:
        """
        Filter out dataframe keys that are not tags

        @param dataframe_keys:
        @return:
        """
        return (
            k
            for k in dataframe_keys
            if not k.startswith("_") and k not in ["result", "table"]
        )

    def __get_influxdb_lines(self, df: pd.DataFrame) -> str:
        """
        Convert the Pandas Dataframe into InfluxDB line protocol.

        The dataframe should be similar to results received from query_api.query_data_frame()

        Not quite sure if this supports all kinds if InfluxDB schemas.
        It might be that influxdb_client package could be used as an alternative to this,
        but I'm not sure about the authorizations and such.

        Protocol description: https://docs.influxdata.com/influxdb/v2.0/reference/syntax/line-protocol/
        """
        logger.info(f"Exporting {df.columns}")

        if df.empty:
            logger.debug(f"No data points for this")
            return ""

        line: str
        # Only applies to Homeassistant data migration.
        # self.__pivot guides if this is straight conversion/export or pivoting the measurements into
        # unit and having the entity ids as measurements.
        if self.pivot:
            line = df["entity_id"]
            line = df["domain"] + "." + line
        else:
            line = df["_measurement"]

        for col_name in self.__get_tag_cols(df):
            line += ("," + col_name.replace(r" ", r"\ ").replace(r",", r"\,").replace(r"=", r"\=") + "=") \
                + df[col_name].astype(str).str.replace(r" ",
                                                       r"\ ").replace(r",", r"\,").replace(r"=", r"\=")

        if self.pivot:
            line += ("," + "unit_of_measurement=") + df["_measurement"].astype(
                str).str.replace(r" ", r"\ ").replace(r",", r"\,").replace(r"=", r"\=")

        line += (
                " "
                + df["_field"].astype(str).str.replace(r" ",
                                                       r"\ ").replace(r",", r"\,").replace(r"=", r"\=")
                + "="
                + df["_value"].map(lambda x: (("\"" + (x.replace("\"", "\\\"").replace(
                    "\n", "\\n").replace("\r", "\\r")) + "\"") if (type(x) is str) else str(x)))
                + " "
                + df["_time"].astype(int).astype(str)
        )
        return "\n".join(line)


def main(args: Dict[str, str]):
    logger.info("args: " + str(args.keys()))
    bucket = args.pop("bucket")
    vm_url = args.pop("VM_ADDR")
    if vm_url is None:
        vm_url = os.environ['VM_ADDR']
    dry_run = bool(args.pop("dry_run"))
    pivot = bool(args.pop("pivot"))

    print(f"Dry run {dry_run} Pivot {pivot}")

    for k, v in args.items():
        if v is not None:
            os.environ[k] = v
        logger.info(f"Using {k}={os.getenv(k)}")

    migrator = InfluxMigrator(bucket, vm_url, chunksize=5000, dry_run=dry_run, pivot=pivot)
    migrator.influx_connect()
    migrator.migrate()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Script for exporting InfluxDB data into victoria metrics instance. \n"
                    " InfluxDB settings can be defined on command line or as environment variables"
                    " (or in .env file if python-dotenv is installed)."
                    " InfluxDB related args described in \n"
                    "https://github.com/influxdata/influxdb-client-python#via-environment-properties"
    )
    parser.add_argument(
        "bucket",
        type=str,
        help="InfluxDB source bucket",
    )
    parser.add_argument(
        "--INFLUXDB_V2_ORG",
        "-o",
        type=str,
        help="InfluxDB organization",
    )
    parser.add_argument(
        "--INFLUXDB_V2_URL",
        "-u",
        type=str,
        help="InfluxDB Server URL, e.g., http://localhost:8086",
    )
    parser.add_argument(
        "--INFLUXDB_V2_TOKEN",
        "-t",
        type=str,
        help="InfluxDB access token.",
    )
    parser.add_argument(
        "--INFLUXDB_V2_SSL_CA_CERT",
        "-S",
        type=str,
        help="Server SSL Cert",
    )
    parser.add_argument(
        "--INFLUXDB_V2_TIMEOUT",
        "-T",
        type=str,
        help="InfluxDB timeout",
    )
    parser.add_argument(
        "--INFLUXDB_V2_VERIFY_SSL",
        "-V",
        type=str,
        help="Verify SSL CERT",
    )
    parser.add_argument(
        "--VM_ADDR",
        "-a",
        type=str,
        help="VictoriaMetrics server URL, e.g., http://localhost:8428",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action='store_true',
        default=False,
        help="Dry run",
    )
    parser.add_argument(
        "--pivot",
        "-P",
        action='store_true',
        default=False,
        help="Pivot entity_id to be measurement",
    )

    main(vars(parser.parse_args()))
    print("All done")
