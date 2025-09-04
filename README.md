# pets2026-first-party-tracking-artifact
Artifact for our `Ad Personalization and Transparency in Mobile Ecosystems: A Comparative Analysis of Google’s and Apple’s EU App Stores` paper to be published in Proceedings on Privacy Enhancing Technologies 2026 (Issue 1).

## Global Setup
Copy sample.env to .env and set values to reflect your environment:
If you use our docker container for the database (see [Dockerfile](./stats-and-figures/database/Dockerfile)), you can leave the default `DB_*`values.

The API token should be set to a random value of a sufficient length, e.g., by running
```bash
tr -dc A-Za-z0-9 </dev/urandom | head -c 50; echo
```

In case you want to use features of the harvester API that retrieve information through Apple's App Store API, a valid Apple bearer token needs to be added to .env.
This token can be retrieved from the traffic of a jailbroken iPhone while accessing the App Store. Use tools like Proxyman or mitmproxy to inspect the iPhones traffic.


## Components
This section describes the different components we designed for this paper, structured as different subdirectories in this repository.
For detailed information, refer to the `README.md` in each subdirectory.

## Account Creator
The [account-creator][./account-creator/] directory contains helper scripts for creating database entries for experiment accounts as well as Selenium-based scripts aiding in the creation of Google and Apple accounts.

## Android Ad Extraction
Our code used to extract ads from Google's Play Store on Android is located in [android-ad-extraction](./android-ad-extraction/).
Please refer to the `README.md` there for install and usage instructions.

## Harvester Api
[harvester-api][./harvester-api/] contains our REST API that manages database access and the service fetching app details from Google and Apple.
Additionally, some helper scripts to manage our persona entries are located therein too.

## iOS Ad Extraction
[ios-ad-extraction][./ios-ad-extraction/] is the iOS counterpart to the [android-ad-extraction](./android-ad-extraction/) component.
It is used to extract ad data from iPhones.

## Stats and Figures
The [stats-and-figures][./stats-and-figures/] directory contains scripts to reproduce the figures and, to some extent, tables from our paper.
