packages = c("DBI","RPostgres")

source("r_scripts/util.r")
probe_and_install_packages(packages)

## SQL Statements Android
sql_datapoints_android <- "
SELECT ad_data.*, app_detail.data->>'applicationCategory' AS store_category
FROM ad_data
JOIN app_detail ON app_detail.id = ad_data.app_id
WHERE experiment_id = $1
ORDER BY time;
"

sql_categories_android <-"
SELECT DISTINCT app_detail.data->>'applicationCategory'
AS store_category
FROM app_detail
WHERE platform = 'android'
ORDER BY store_category ASC;
"

## SQL Statements iOS

sql_datapoints_ios <- "
SELECT ad_data.*, app_detail.data->'relationships'->'genres'->'data'->0->>'id' as store_category_id, app_detail.data->'relationships'->'genres'->'data'->0->'attributes'->>'name' as store_category
FROM ad_data
JOIN app_detail ON app_detail.id = ad_data.app_id
WHERE experiment_id = $1
ORDER BY time;
"

sql_categories_ios <-"
SELECT DISTINCT js->>'id' as id, js->'attributes'->>'name' AS store_category
FROM app_detail, jsonb_array_elements(app_detail.data->'relationships'->'genres'->'data') as js
WHERE platform = 'ios'
ORDER BY store_category ASC;
"

## platform independent SQL statements
sql_experiments_by_group <- "
SELECT a.id AS id_control, b.id AS id_treatment, c.id AS id_control_np, d.id AS id_treatment_np, a.sub_group_id AS sub_group_id
FROM experiment a
JOIN experiment b ON a.sub_group_id = b.sub_group_id
JOIN experiment c ON a.account_email = c.account_email
JOIN experiment d ON b.account_email = d.account_email
WHERE   a.group_id = $1
    AND b.group_id = $1
    AND c.group_id = $1
    AND d.group_id = $1
    AND a.id != b.id AND c.id != d.id
    AND a.treatment = False
    AND a.personalized = True
    AND b.treatment = True
    and b.personalized = True
    AND c.personalized = False
    AND c.treatment = False
    AND d.personalized = False
    AND d.treatment = True
ORDER BY id_control, id_treatment, id_control_np, id_treatment_np;
"


sql_experiment_details <- "
SELECT experiment.id, experiment.device_serial, experiment.comment, experiment.account_email, experiment.treatment, experiment.personalized, account.birth
FROM experiment
JOIN account ON experiment.account_email = account.email
WHERE experiment.id = $1;"

## Functions
get_db_connection <- function() {
    con <- dbConnect(RPostgres::Postgres(),
                 user=Sys.getenv("DB_USER"),
                 password=Sys.getenv("DB_PASSWORD"),
                 dbname=Sys.getenv("DB_NAME"),
                 port=Sys.getenv("DB_PORT"),
                 host=Sys.getenv("DB_HOST"))
    return(con)
}

