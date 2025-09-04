# Study Dataset: Advertisements and Recommendations of Apple's and Google's EU App Stores
This dataset is an artifact for our `Ad Personalization and Transparency in Mobile Ecosystems: A Comparative Analysis of Google’s and Apple’s EU App Stores` paper published in Proceedings on Privacy Enhancing Technologies 2026 (Issue 1).

It consists of the PostgreSQL export primarily containing advertisement and recommendation data measured on Google's Play Store and Apple's App Store within the region of Germany.
This data was produced by carefully constructing personas of interest, signalling them on devices, and then measuring the ads and recommendations that they receive for a given period.

## Usage Instructions
We recommend to use the Dockerfile that is part of our repository (https://github.com/seemoo-lab/appstore-ad-tools).
It provides a ready to use setup for importing this dataset and exposes a working PostgreSQL instance.

If you wish to manually set up your database, you need postgresql installed and running (tested on postgresql 15.14).

Use this command to import the dataset:
```bash
pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v app_store_data.pgdump
```

## Redaction
We removed some sensitive data covering our Apple and Google accounts and sim cards.
In these instances, we replaced the corresponding entries with the placeholder `REDACTED` in the exported database dump.  
This should not negatively impact the reproducibility of our results.

## Documentation
In the following, we document the different tables contained in this dataset.

### Table `ad_data`
The 'primary' table containing the ads and recommendations we measure.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | integer | PRIMARY KEY (composite) | Incremental ad data entry ID |
| `experiment_id` | integer | PRIMARY KEY (composite), FOREIGN KEY → experiment.id | Associated experiment (see `experiment` table) |
| `time` | timestamp | | Time at which this ad was observed. |
| `label` | text | | Name of the measured app (either an ad or a recommendation) as displayed in the App store.|
 | `sub_label` | text | | Sub label. On Android this includes the star rating and a short `tag` that is not directly corresponding to the app's category. On iOS, this field contains a short description or catchphrase. |
| `app_id` | integer | FOREIGN KEY → app_detail.id | Link to the `app_detail` table with the metadata that has been retrieved based on this item's label field.|
| `from_search_page` | boolean | | Whether ad was from search page or today page (iOS only) |
| `type` | text | | Measured item type, either `'ad'` or `'suggestion'`.__Note: We primarily use the term `recommendations` instead of `suggestion` when referring to suggested apps in our paper or other documentation._ | 

### Table `account`
Stores account information for Google and iOS accounts.
We used this data to automatically login accounts on devices.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `email` | text | PRIMARY KEY, NOT NULL | Account's email address (unique identifier) |
| `sur_name` | text | | Account's surname/last name |
| `first_name` | text | | Account's first name |
| `password` | text | | Account's password in plaintext |
| `birth` | timestamp | | Account's birth date |
| `gender` | text | | Account's gender |
| `phonenumber` | text | FOREIGN KEY → sim.phonenumber | Associated phone number |
| `street` | text | | Street address (only used for iOS accounts) |
| `city` | text | | City (only used for iOS accounts) |
| `postalcode` | integer | | Postal/ZIP code (only used for iOS accounts) |
| `street_number` | integer | | Street number (only used for iOS accounts) |
| `country` | text | | Country (only used for iOS accounts) |
| `persona_id` | integer | FOREIGN KEY → persona.id | Associated account persona|
| `created_at` | timestamp | | Account creation timestamp |
| `platform` | text | | Platform type, either `'android'` or `'ios'` |

#### Table `account_log`
Tracks account logins and logouts and additionally extraction steps (iOS only).  
_Note: We introduced this table after the preliminary experiments, so some data might be missing._ 

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | bigint | PRIMARY KEY, AUTO INCREMENT | Unique log entry ID |
| `account_email` | text | | Associated account email |
| `time` | timestamp | | Action timestamp |
| `device_serial` | text | | Device serial |
| `action` | text | | Action performed, one of: 'logout', 'inactive', 'probe_login_error', 'enablePersonalization', 'login', 'disablePersonalization', 'extract_unpersonalized', 'signal', 'logout (factory reset)', 'probe_login_success', 'extract' |

### Table `sim`
Stores SIM card information and is used to implement rudimentary "locking" to prevent multiple devices from trying to use the same SIM simultaneously.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `phonenumber` | text | PRIMARY KEY, NOT NULL | Phone number (unique identifier) |
| `address` | text | | URL used by the provider for SIM activation. Our source code uses this URL to generate the token for manual eSIM registration.  |
| `activation_code` | text | | SIM activation code |
| `confirmation_code` | text | | SIM Confirmation code |
| `pin` | text | | SIM PIN code |
| `puk` | text | | SIM PUK code |
| `serial` | text | | SIM serial number |
| `comment` | text | | Additional comments we used to mark special test SIM cards. |
| `locked` | boolean | | Whether SIM is locked, to avoid simultaneous re-use. |
| `broken` | boolean | | Whether SIM is 'broken', sometimes our provider would temporarily (?) block eSIM activation attempts for specific sim cards. |

### Table `sim_insertion_log`
Tracks when SIM cards are inserted into devices.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `phonenumber` | text | PRIMARY KEY, NOT NULL | Phone number (unique identifier) links into `sim` table. |
| `device_serial` | text | | Device serial number |
| `time` | timestamp | PRIMARY KEY, NOT NULL | SIM Insertion timestamp. |

### Table `app`
Stores platform dependent application identifiers.
This table is used in the context of personas, which are assigned entries from this table.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | integer | PRIMARY KEY, AUTO INCREMENT | Unique app ID |
| `google_id` | text | | Google Play Store app identifier. |
| `apple_id` | text | | Apple App Store app identifier. |
| `name` | text | | Application name |

### Table `app_detail`
Stores detailed application information in JSON format as fetched by our backend service.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | integer | PRIMARY KEY, AUTO INCREMENT | Unique detail ID |
| `data` | jsonb | | Application details in JSON format as extracted from the respective Google and Apple store endpoints. |
| `updated_on` | timestamp | | Last update timestamp |
| `label` | text | | The name of the app as it appears in the respective app store.
| `platform` | text | | Platform, either `'android'` or `'ios'`. |

### Table `app_install_log`
Tracks app installations by personas.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | integer | PRIMARY KEY, AUTO INCREMENT | Unique installation log ID |
| `account_email` | text | FOREIGN KEY → account.email | Account that installed the app |
| `app_id` | integer | FOREIGN KEY → app.id | App identifier of the application that has been installed |
| `time` | timestamp | | Installation timestamp |

### Table `experiment`
Defines experiment configurations that are executed on a single device.
In the context of our study, a full `experiment run` would consist of multiple individual entries in this table that reflect treatment, control, personalized, and non-personalized variants.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | integer | PRIMARY KEY, AUTO INCREMENT | Unique experiment ID |
| `platform` | text | | Platform used for experiment, either `'android'` or `'ios'` |
| `device_serial` | text | | Device serial number that this specific configuration was executed on |
| `comment` | text | | Experiment description/notes |
| `account_email` | text | FOREIGN KEY → account.email | Account email that is used on the device.|
| `group_id` | text | | Experimental group identifier, for example, a UUID that is consistent for all `Shopping` persona experiments.|
| `sub_group_id` | text | | Sub-group identifier tying together the four variants for a single simultaneous execution on two devices.|
| `treatment` | boolean | | Marks whether a control or treatment persona is used. |
| `personalized` | boolean | | Whether ad personalization is active or disabled. |

### Table `persona`
Defines personas which are then signaled on the devices to measure differences in the received ads and recommendations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | integer | PRIMARY KEY, AUTO INCREMENT | Unique persona ID |
| `comment` | text | | Persona description outlining the relevant aspects of this persona. |

### Table `link_persona_app`
Links personas to the applications that they should install on a device during the signalling process.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | integer | PRIMARY KEY, AUTO INCREMENT | Unique link ID |
| `persona_id` | integer | FOREIGN KEY → persona.id | Associated persona |
| `app_id` | integer | FOREIGN KEY → app.id | App to install during signalling. |
