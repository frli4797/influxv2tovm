## Migrate data from InfluxDB v2 to VictoriaMetrics with Home Assistant support
This project provides a Python script to import data from InfluxDB >=2.0 to VictoriaMetrics and is highly inspired and developed originally from
https://github.com/jonppe/influx_to_victoriametrics/ and then significant extra work, including [Home Assistant](https://www.home-assistant.io) support, from Fredrik J-L at https://github.com/frli4797/influxv2tovm/

The [command line tool](https://github.com/VictoriaMetrics/VictoriaMetrics/blob/master/docs/vmctl.md) packaged with VictoriaMetrics provides similar features for InfluxDB 1.X, although without specific support for Home Assistant.

Every unique time series is queried one by one and exported to VictoriaMetrics. For large datasets the metrics are broken into chunks of 5000 and submitted in batches using the legacy Influx [Line Protocol API](https://archive.docs.influxdata.com/influxdb/v0.9/write_protocols/write_syntax/).

## About this fork
This project is a fork based on the [fri4797](https://github.com/frli4797/influxv2tovm) fork of the original project developed by [jonppe](https://github.com/jonppe/influx_to_victoriametrics/). The initial project was designed to migrate multiple InfluxDB v2 buckets into a single VictoriaMetrics DB each annotated with a key designating the DB source for delineation. The limitations of that version is that the migration was done by entire metric and in a sufficiently large dataset a single metric could exceed the resources of the runtime.

The original project was forked by Fredrick J-L in summer 2024 where it was substantially reworked to add chunking of the data into controlled transaction sizes and support for InfluxDBs populated with [Home Assistant](https://www.home-assistant.io) data. Home Assistant (HA) is a home automation system that generates many data points stored in a SQL DB and it is not unusual for deployers to supplement the SQL DB with a time series DB for historical data, usually InfluxDB v1 or v2.

As Influx has pivoted to enterprise customers, many HA users have been inspired by the [VictoriaMetrics Add-on](https://github.com/fuslwusl/homeassistant-addon-victoriametrics) developed by fuslwusl to use VictoriaMetrics (VM) as it more closely matched the use case. The HA integration is highly configurable and other integrations can provide metrics leading to a highly diverse dataset.

This project uses the legacy Influx [Line Protocol API](https://archive.docs.influxdata.com/influxdb/v0.9/write_protocols/write_syntax/) to submit metrics to VM and the heterogenous nature of HA data sources exposed a number of flaws in the original project that did not sanitize the input data and created API calls that did not comply with the ingest specification.


## Usage
~~~~
./influx_export.py -h
usage: influxv2tovm.py [-h] [--INFLUXDB_V2_ORG INFLUXDB_V2_ORG] [--INFLUXDB_V2_URL INFLUXDB_V2_URL] [--INFLUXDB_V2_TOKEN INFLUXDB_V2_TOKEN]
                        [--INFLUXDB_V2_SSL_CA_CERT INFLUXDB_V2_SSL_CA_CERT] [--INFLUXDB_V2_TIMEOUT INFLUXDB_V2_TIMEOUT]
                        [--INFLUXDB_V2_VERIFY_SSL INFLUXDB_V2_VERIFY_SSL] [--VM_ADDR VM_ADDR]
                        [--dry-run]
                        [--pivot]
                        bucket

Script for exporting InfluxDB data into victoria metrics instance. InfluxDB settings can be defined on command line
or as environment variables (or in .env file  if python-dotenv is installed).

InfluxDB related args described in https://github.com/influxdata/influxdb-client-python#via-environment-properties

positional arguments:
  bucket                InfluxDB source bucket, which is also added to the tag "db" in VM

optional arguments:
  -h, --help            show this help message and exit
  --INFLUXDB_V2_ORG INFLUXDB_V2_ORG, -o INFLUXDB_V2_ORG
                        InfluxDB organization
  --INFLUXDB_V2_URL INFLUXDB_V2_URL, -u INFLUXDB_V2_URL
                        InfluxDB Server URL, e.g., http://localhost:8086
  --INFLUXDB_V2_TOKEN INFLUXDB_V2_TOKEN, -t INFLUXDB_V2_TOKEN
                        InfluxDB access token.
  --INFLUXDB_V2_SSL_CA_CERT INFLUXDB_V2_SSL_CA_CERT, -S INFLUXDB_V2_SSL_CA_CERT
                        Server SSL Cert
  --INFLUXDB_V2_TIMEOUT INFLUXDB_V2_TIMEOUT, -T INFLUXDB_V2_TIMEOUT
                        InfluxDB timeout
  --INFLUXDB_V2_VERIFY_SSL INFLUXDB_V2_VERIFY_SSL, -V INFLUXDB_V2_VERIFY_SSL
                        Verify SSL CERT.
  --VM_ADDR VM_ADDR, -a VM_ADDR
                        VictoriaMetrics server
  --dry-run, -n         Dry run, don't write changes to VM
  --pivot, -P           Pivot entity_id to be measurement, this is specific to Home Assistant metrics
~~~~

## Running in a Dev Container
It is likely that most people using this tool will use it once to migrate a data set and never again. The target audience is therefore likely not a developer, familiar with Python or even has a workable Python environment.

To simplify usage of this tool this repo includes a definition for a Dev Container. This is compatible with many developer environments including VSCode and Github Codespaces. On opening the workspace you will be prompted to reopen the project in a Dev Container.

This will download an Ubuntu container with Python pre-installed and then install all the project library dependencies before opening a terminal prompt. If using VSCode then the Python support extensions will be installed and there is a Debugger launch definition should you want to step through the code.

The python tool supports setting parameters from environment variables. If you need to run the tool multiple times it might be easier to define these parameters as environment variables by editing the `./devcontainer/.devcontainer.json` file. Alternatively set them in the .env file created at the root of the project when the dev container is started.

## Home Assistant migration
If the source bucket was populated by Home Assistant then it will need some specific transforming, specifically the _measurement column moved to a unit_of_measurement label and replaced with the Home Assistant EntityID.

It is recommended to run this tool in a Dev Container as it vastly simplifies configuring the Python runtime environment. While Dev Containers are widely supported such as Github Codespaces it is probable that your VM and Influx endpoints are not publically exposed so the best local tool would be [VSCode](https://code.visualstudio.com). See the instruction above on how to use a Dev Container.

If you are using the [VictoriaMetrics Addon](https://github.com/fuslwusl/homeassistant-addon-victoriametrics) then the VM_ADDR parameter or environment variable should be set to the url of Home Assistant on port 8428, e.g. `http://homeassistant.local:8428`. You will need to get the Influx URL, token and org from your InfluxDB v2 installation. Once your Dev Container is running there should be a terminal pane to run the following:
~~~~
./influxv2tovm.py --pivot --dry-run home_assistant
~~~~

If this execution looks good then simply re-run the above command omitting the `--dry-run` parameter.

---
Author: Max Lyth

Thanks to: Johannes Aalto & Fredrik J-L

SPDX-License-Identifier: Apache-2.0
