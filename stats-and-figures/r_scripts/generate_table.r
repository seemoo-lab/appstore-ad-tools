packages = c("dplyr", "xtable", "tidyr")

source("r_scripts/util.r")
probe_and_install_packages(packages)

source("r_scripts/constants.r")

## read android data
df_android <- read.csv("gen/results/android/stats_.csv")
df_android_suggestions <- read.csv("gen/results/android_suggestion/stats_.csv")


## read ios data
df_ios_all <- read.csv("gen/results/ios/stats_all.csv")
df_ios_search <- read.csv("gen/results/ios/stats_search.csv")
df_ios_today <- read.csv("gen/results/ios/stats_today.csv")

df_ios_baseline_all <- read.csv("gen/results/ios_baseline/stats_all.csv")
df_ios_baseline_search <- read.csv("gen/results/ios_baseline/stats_search.csv")
df_ios_baseline_today <- read.csv("gen/results/ios_baseline/stats_today.csv")

all_results <- data.frame()

string_android <- "Android"
string_ios <- "iOS (All)"
string_ios_search <- "iOS (Search Page)"
string_ios_today <- "iOS (Today Page)"

string_account <- "Account Parameter"
string_baseline <- "Baseline"
string_persona <- "Interest Groups"




count_chi_square <- function(data, group_ids, suggestion, platform, comment) {
    c_s <- data %>% filter(aggregated == FALSE) %>% 
                    filter(group_id %in% group_ids) %>% 
                    filter(p < 0.05) %>% 
                    mutate(personalized=case_when((grepl("_p_np", personalized, fixed=TRUE) & grepl("CONTROL", toupper(comment_control), fixed=TRUE)) ~ "_p_np_c", .default = personalized)) %>%
                    mutate(personalized=case_when((grepl("_p_np", personalized, fixed=TRUE) & grepl("TREATMENT", toupper(comment_control), fixed=TRUE)) ~ "_p_np_t", .default = personalized)) %>%
                    count(personalized) %>% 
                    spread(personalized,n) %>%
                    mutate(suggestion = suggestion, significant = TRUE, platform = platform)
    if(nrow(c_s) == 0) {
        c_s = data.frame(0)
        c_s$suggestion <- suggestion
        c_s$significant <- TRUE
        c_s$platform <- platform
    }
    c_n <- data %>% filter(aggregated == FALSE) %>% 
                    filter(group_id %in% group_ids) %>% 
                    filter(p >= 0.05) %>% 
                    mutate(personalized=case_when((grepl("_p_np", personalized, fixed=TRUE) & grepl("CONTROL", toupper(comment_control), fixed=TRUE)) ~ "_p_np_c", .default = personalized)) %>%
                    mutate(personalized=case_when((grepl("_p_np", personalized, fixed=TRUE) & grepl("TREATMENT", toupper(comment_control), fixed=TRUE)) ~ "_p_np_t", .default = personalized)) %>%
                    count(personalized) %>% 
                    spread(personalized,n) %>%
                    mutate(suggestion = suggestion, significant = FALSE, platform = platform)
                    
    if(nrow(c_n) == 0) {
        c_n = data.frame(0)
        c_n$suggestion <- suggestion
        c_n$significant <- FALSE
        c_n$platform <- platform
    }
    #check if empty
    

    results <- bind_rows(c_n, c_s)
    results$comment <- comment
    return(results)
}



all_results <- all_results %>% bind_rows(count_chi_square(df_android_suggestions, group_ids_android_account_parameter, TRUE, string_android, string_account))
all_results <- all_results %>% bind_rows(count_chi_square(df_android_suggestions, group_ids_android_personas, TRUE, string_android, string_persona))
all_results <- all_results %>% bind_rows(count_chi_square(df_android_suggestions, group_ids_android_baseline, TRUE, string_android, string_baseline))

all_results <- all_results %>% bind_rows(count_chi_square(df_android, group_ids_android_account_parameter, FALSE, string_android, string_account))
all_results <- all_results %>% bind_rows(count_chi_square(df_android, group_ids_android_personas, FALSE, string_android, string_persona))
all_results <- all_results %>% bind_rows(count_chi_square(df_android, group_ids_android_baseline, FALSE, string_android, string_baseline))

all_results <- all_results %>% bind_rows(count_chi_square(df_ios_all, group_ids_ios_account_parameter, FALSE, string_ios, string_account))
all_results <- all_results %>% bind_rows(count_chi_square(df_ios_all, group_ids_ios_personas, FALSE, string_ios, string_persona))
all_results <- all_results %>% bind_rows(count_chi_square(df_ios_baseline_all, group_ids_ios_baseline, FALSE, string_ios, string_baseline))

all_results <- all_results %>% bind_rows(count_chi_square(df_ios_search, group_ids_ios_account_parameter, FALSE, string_ios_search, string_account))
all_results <- all_results %>% bind_rows(count_chi_square(df_ios_search, group_ids_ios_personas, FALSE, string_ios_search, string_persona))
all_results <- all_results %>% bind_rows(count_chi_square(df_ios_baseline_search, group_ids_ios_baseline, FALSE, string_ios_search, string_baseline))

all_results <- all_results %>% bind_rows(count_chi_square(df_ios_today, group_ids_ios_account_parameter, FALSE, string_ios_today, string_account))
all_results <- all_results %>% bind_rows(count_chi_square(df_ios_today, group_ids_ios_personas, FALSE, string_ios_today, string_persona))
all_results <- all_results %>% bind_rows(count_chi_square(df_ios_baseline_today, group_ids_ios_baseline, FALSE, string_ios_today, string_baseline))

test <- all_results
all_results <- all_results %>%  select(-X0) %>%
                                replace_na(list("_np_np" = 0, "_p_np_c" = 0, "_p_np_t" = 0, "_p_p" = 0)) %>%
                                replace_na(list("np" = 0, "p" = 0, "p_np" = 0)) %>%
                                pivot_wider(names_from = comment, values_from = "_np_np":"_p_p", names_vary = "slowest", values_fill = 0, names_sort = TRUE)


write.csv(all_results, "gen/chi_square_table.csv")
