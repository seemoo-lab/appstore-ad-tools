# ios-ad-extraction
iOS/Apple part of our ad extraction instrumentation.

## Prerequisites
- Xcode 16.4  and xcode command line tools
- python 3.12
- 1 or 2 iPhone 15 running iOS 17.4

Other software versions might work too, but we tested only the configuration above.

## Setup
Setup a python venv and install the dependencies given in requirements.txt:
```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
Adapt required configuration values to match your environment:
- In `test_device.mobileconfig`: Replace <WIFI_PASSWORD> and <WIFI_SSID> with the WiFi credentials your iPhone should join after setup.

## Building
Open the xcodeproject, set signing information and build it for testing via xcode ui.

## Running experiments
`ios_device.py` is the entry point for all experiments, it is the glue code managing all the subcomponents.
It should be run with an experiment configuration file, for example:
```sh
python ios_device.py --from_file experiments/example_experiment.csv
```

See the `python ios_device.py --help` file for all supported options.
