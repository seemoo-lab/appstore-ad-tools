readRenviron("../.env")

## set seed
set.seed(42)

source("r_scripts/constants.r")
source("r_scripts/util.r")
source("r_scripts/database.r")
source("r_scripts/tests.r")

packages = c("dplyr")

source("r_scripts/util.r")
probe_and_install_packages(packages)


time_interval <- 60
print(getwd())
compute_chi_square <- function(platform, path_platform, ad_source, filter_type, baseline){
    print(sprintf("starting permutation tests for Platform: %s, Path: %s, ad_source: %s, filter: %s, baseline: %s", platform, path_platform, ad_source, filter_type, baseline))
    if(platform == "android") {
        ad_source <- ""
    }


    if(platform == "ios") {
        if(baseline==TRUE){
            group_ids <- group_ids_ios_baseline
        } else {
            group_ids <- group_ids_ios
        }
        sql_categories <- sql_categories_ios
        sql_datapoints <- sql_datapoints_ios
    } else {
        if(baseline==TRUE){
            group_ids <- group_ids_android_baseline
        } else {
            group_ids <- group_ids_android
        }
        sql_categories <- sql_categories_android
        sql_datapoints <- sql_datapoints_android
    }


    ##keep track of all data
    data_control_all <- data.frame()
    data_treatment_all <- data.frame()
    data_control_all_np <- data.frame()
    data_treatment_all_np <- data.frame()

    ## keep track of all statistical tests
    results <- data.frame(group_id=character(0), exp_control=numeric(0), exp_treatment=numeric(0), chisq=numeric(0), p=numeric(0), cosine=numeric(0), email_control=character(0), email_treatment=character(0), comment_control=character(0), comment_treatment=character(0), personalized=character(0), device_treatment=character(0), device_control=character(0), aggregated=logical(0))


    ##loop over all group ids

    for(group_id in group_ids) {
        ## get db connection
        con <- get_db_connection()

        ## fetch categories
        if(platform == "ios") {
            categories <- dbGetQuery(con, sql_categories)
            categories <- filter(categories, !id %in% game_categories_ios)
        } else {
            categories <- dbGetQuery(con, sql_categories) %>% mutate(store_category = replace(store_category, substr(store_category,1,5) == "GAME_", "GAME"))
            categories <- categories[!duplicated(categories),]
        }
        
        ## fetch experiments
        experiments <- dbGetQuery(con, sql_experiments_by_group, params=list(group_id))

        ##keep track of all data of this group
        data_control_group <- data.frame()
        data_treatment_group <- data.frame()
        data_control_group_np <- data.frame()
        data_treatment_group_np <- data.frame()
        
        ## loop over experiments of group
        for(i in 1:nrow(experiments)) {
            # short-hand access for experiment ids
            ic <- experiments[i, 'id_control']
            it <- experiments[i, 'id_treatment']
            ic_np <- experiments[i, 'id_control_np']
            it_np <- experiments[i, 'id_treatment_np']
            sub_group_id <- experiments[i, 'sub_group_id']

            print(sprintf("computing experiments %s, %s, %s, %s", ic, it, ic_np, it_np))
            ## get experiment metadata
            # get experiment details
            ic_details <- dbGetQuery(con, sql_experiment_details, params=list(ic))
            it_details <- dbGetQuery(con, sql_experiment_details, params=list(it))
            ic_details_np <- dbGetQuery(con, sql_experiment_details, params=list(ic_np))
            it_details_np <- dbGetQuery(con, sql_experiment_details, params=list(it_np))       

            # make data classes
            meta_control = new('experiment_metadata',
                        id=ic_details[1, 'id'],
                        email=ic_details[1, 'account_email'],
                        comment=ic_details[1, 'comment'],
                        birth=ic_details[1, 'birth'],
                        device=ic_details[1, 'device_serial'],
                        treatment=ic_details[1, 'treatment'],
                        personalized=ic_details[1, 'personalized'])
            meta_treatment = new('experiment_metadata',
                        id=it_details[1, 'id'],
                        email=it_details[1, 'account_email'],
                        comment=it_details[1, 'comment'],
                        birth=it_details[1, 'birth'],
                        device=it_details[1, 'device_serial'],
                        treatment=it_details[1, 'treatment'],
                        personalized=it_details[1, 'personalized'])
            meta_control_np = new('experiment_metadata',
                            id=ic_details_np[1, 'id'],
                            email=ic_details_np[1, 'account_email'],
                            comment=ic_details_np[1, 'comment'],
                            birth=ic_details_np[1, 'birth'],
                            device=ic_details_np[1, 'device_serial'],
                            treatment=ic_details_np[1, 'treatment'],
                            personalized=ic_details_np[1, 'personalized'])
            meta_treatment_np = new('experiment_metadata',
                            id=it_details_np[1, 'id'],
                            email=it_details_np[1, 'account_email'],
                            comment=it_details_np[1, 'comment'],
                            birth=it_details_np[1, 'birth'],
                            device=it_details_np[1, 'device_serial'],
                            treatment=it_details_np[1, 'treatment'],
                            personalized=it_details_np[1, 'personalized'])

            ## fetch data
            data_control <- dbGetQuery(con, sql_datapoints, params=list(meta_control@id))
            data_treatment <- dbGetQuery(con, sql_datapoints, params=list(meta_treatment@id))
            data_control_np <- dbGetQuery(con, sql_datapoints, params=list(meta_control_np@id))
            data_treatment_np <- dbGetQuery(con, sql_datapoints, params=list(meta_treatment_np@id))


            ##merge experiment data into dataset
            data_control$device <- meta_control@device
            data_control$comment <- meta_control@comment
            data_control$treatment <- meta_control@treatment
            data_control$personalized <- meta_control@personalized
            data_control$sub_group_id <- sub_group_id
            data_control$treatment_personalized_string <- 'c_p'
    

            data_treatment$device <- meta_treatment@device
            data_treatment$comment <- meta_treatment@comment
            data_treatment$treatment <- meta_treatment@treatment
            data_treatment$personalized <- meta_treatment@personalized
            data_treatment$sub_group_id <- sub_group_id
            data_treatment$treatment_personalized_string <- 't_p'

            data_control_np$device <- meta_control_np@device
            data_control_np$comment <- meta_control_np@comment
            data_control_np$treatment <- meta_control_np@treatment
            data_control_np$personalized <- meta_control_np@personalized
            data_control_np$sub_group_id <- sub_group_id
            data_control_np$treatment_personalized_string <- 'c_np'

            data_treatment_np$device <- meta_treatment_np@device
            data_treatment_np$comment <- meta_treatment_np@comment
            data_treatment_np$treatment <- meta_treatment_np@treatment
            data_treatment_np$personalized <- meta_treatment_np@personalized
            data_treatment_np$sub_group_id <- sub_group_id
            data_treatment_np$treatment_personalized_string <- 't_np'

            ## filter on ad source
            if(ad_source == "search") {
                data_control <- data_control %>% filter(from_search_page == TRUE)
                data_treatment <- data_treatment %>% filter(from_search_page == TRUE)
                data_control_np <- data_control_np %>% filter(from_search_page == TRUE)
                data_treatment_np <- data_treatment_np %>% filter(from_search_page == TRUE)
            } else if (ad_source == "today") {
                data_control <- data_control %>% filter(from_search_page == FALSE)
                data_treatment <- data_treatment %>% filter(from_search_page == FALSE)
                data_control_np <- data_control_np %>% filter(from_search_page == FALSE)
                data_treatment_np <- data_treatment_np %>% filter(from_search_page == FALSE)
            }


            ## filter by ad only
            data_control <- data_control %>% filter(type == filter_type)
            data_treatment <- data_treatment %>% filter(type == filter_type)
            data_control_np <- data_control_np %>% filter(type == filter_type)
            data_treatment_np <- data_treatment_np %>% filter(type == filter_type)

            if((nrow(data_control) == 0) || (nrow(data_treatment) == 0) || (nrow(data_control_np) == 0) || (nrow(data_treatment_np) == 0)) {

                next
            }

            ## merge game categories
            if(platform == "ios"){
                data_control <- clean_categories_ios(data_control, game_categories_ios)
                data_treatment <- clean_categories_ios(data_treatment, game_categories_ios)
                data_control_np <- clean_categories_ios(data_control_np, game_categories_ios)
                data_treatment_np <- clean_categories_ios(data_treatment_np, game_categories_ios)
            } else {
                data_control <- clean_categories_android(data_control)
                data_treatment <- clean_categories_android(data_treatment)
                data_control_np <- clean_categories_android(data_control_np)
                data_treatment_np <- clean_categories_android(data_treatment_np)
            }


            ## append to group data
            data_control_group <- rbind(data_control_group, data_control)
            data_treatment_group <- rbind(data_treatment_group, data_treatment)
            data_control_group_np <- rbind(data_control_group_np, data_control_np)
            data_treatment_group_np <- rbind(data_treatment_group_np, data_treatment_np)

            ## compute statistics
            results <- rbind(results, permutation_test_results(data_control, meta_control, data_treatment, meta_treatment, group_id))
            results <- rbind(results, permutation_test_results(data_control_np, meta_control_np, data_treatment_np, meta_treatment_np, group_id))
            results <- rbind(results, permutation_test_results(data_control, meta_control, data_control_np, meta_control_np, group_id))
            results <- rbind(results, permutation_test_results(data_treatment, meta_treatment, data_treatment_np, meta_treatment_np, group_id))
        }
        ## append to all data
        data_control_all <- rbind(data_control_all, data_control_group)
        data_treatment_all <- rbind(data_treatment_all, data_treatment_group)
        data_control_all_np <- rbind(data_control_all_np, data_control_group_np)
        data_treatment_all_np <- rbind(data_treatment_all_np, data_treatment_group_np)

    }
    ## write statistical results to file
    dir.create(file.path(getwd(), "gen/results"))
    dir.create(file.path(getwd(), sprintf("gen/results/%s", path_platform)))
    write.csv(results, sprintf("gen/results/%s/stats_%s.csv", path_platform, ad_source))
}



# android ads
compute_chi_square("android", "android", "", "ad",FALSE)
# android suggestions
compute_chi_square("android", "android_suggestion", "", "suggestion",FALSE)
# ios all ads
compute_chi_square("ios", "ios", "all", "ad",FALSE)
# ios search ads
compute_chi_square("ios", "ios", "search", "ad",FALSE)
# ios today ads
compute_chi_square("ios", "ios", "today", "ad",FALSE)
# android baseline
compute_chi_square("android", "android_baseline", "", "ad", TRUE)
compute_chi_square("android", "android_baseline_suggestion", "", "suggestion", TRUE)
# ios baseline
compute_chi_square("ios", "ios_baseline", "all", "ad", TRUE)
compute_chi_square("ios", "ios_baseline", "search", "ad", TRUE)
compute_chi_square("ios", "ios_baseline", "today", "ad", TRUE)


source("r_scripts/generate_table.r")
print("summary table written to gen/chi_square_table.csv")