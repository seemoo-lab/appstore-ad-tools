# AdExtractAuto
Android/Google part of our ad extraction instrumentation.
The `hid-setup` subdirectory contains code to manage initial device setup over AoAv2 based on [scrcpy](https://github.com/Genymobile/scrcpy) code.

## Setup
Setup the dependencies, either by running main.py using `uv run --script main.py` or by creating a venv and installing the dependencies given in requirements.txt into it.

## Configuration
Adapt required configuration values to match your environment:
- In `AdExtractAuto/app/src/androidTest/java/com/example/adextractauto/HarvesterAPI.kt`: Set `API_ENDPOINT` and `API_TOKEN`. `API_ENDPOINT` should point to the harvester server.
- In `AdExtractAuto/app/src/androidTest/java/com/example/adextractauto/Devices/AndroidDevice.kt`: Set the `WIFI_NETWORK`, `WIFI_NETWORK_PASS`, and `ESIM_IDENTIFIER` values. The `ESIM_IDENTIFIER` should correspond to the carrier name displayed of your sim cards displayed in the system settings UI.
- In `auth_secret.py`: Set your `API_TOKEN`.
- In `main.py`, line 42: Set the `device_type` dictionary to map your device's IDs to an appropriate type.


## Building
`hid-setup` is built using the `compile_hid_setup.sh` script and can then be run from `build-auto/hid-setup/hid-setup`.

Android automation components are built and run using gradle:
```sh
./gradlew assembleDebugAndroidTest
./gradlew assembleDebug
```

The resulting APKs are installed on the target devices by the experiment code in `main.py` or can be manually installed using
```
 adb install app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk && adb install app/build/outputs/apk/debug/app-debug.apk
```

## Running experiments
`main.py` is the entry point for all experiments, it is the glue code managing all the subcomponents.
It should be run with an experiment configuration file, for exapmle:
```
main.py experiment_configurations/example_experiment.csv
```

See the `experiment_configurations/example_experiment.csv` file for the supported options.

## License
The `hid-setup` subproject includes code derived from [scrcpy](https://github.com/Genymobile/scrcpy), licensed under the Apache License 2.0.
The corresponding copyright applies if not specified otherwise.
