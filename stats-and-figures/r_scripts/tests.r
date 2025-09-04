## Statistical tests go here.
packages = c("rcompanion","wPerm","lsa","stats")

source("r_scripts/util.r")
probe_and_install_packages(packages)

chi_square <- function(data_control, data_treatment, threshold) {
    data_control$group <- "CONTROL"
    data_treatment$group <- "TREATMENT"
    data_complete <- rbind(data_control, data_treatment)
      
    return(chi_square_complete_data(data_complete, threshold))
}

chi_square_complete_data <- function(data_complete, threshold) {
    tab <- table(data_complete$store_category, data_complete$group)

    tab_df <- as.data.frame.matrix(tab)

    tab_df <- tab_df %>% mutate(Other = case_when(CONTROL < threshold & TREATMENT < threshold ~TRUE, .default = FALSE))

    sum_other_control <- sum(tab_df[which(tab_df[,3] == TRUE),1])
    sum_other_treatment <- sum(tab_df[which(tab_df[,3] == TRUE),2])
    tab_df <- tab_df %>% add_row(CONTROL = sum_other_control, TREATMENT = sum_other_treatment) %>% filter(!Other) %>% select(-c("Other")) 

    test <- chisq.test(tab_df)
    return(test)
}


permutation_test <- function(data_control, data_treatment) {
    data_control$group <- "CONTROL"
    data_treatment$group <- "TREATMENT"
    data_complete <- rbind(data_control, data_treatment)
      
    return(permutation_test_complete_data(data_complete))
}

permutation_test_complete_data <- function(data_complete) {
    tab <- table(data_complete$group, data_complete$store_category)
    tab_df <- as.data.frame.matrix(tab) %>% tibble::rownames_to_column("Group")

    test <- perm.ind.test(tab_df, type = "cont", R = 9999)
    return(test)
}

show_perm_hist <- function(perm_test, df) {
    hist(perm_test$Perm.values, freq = FALSE, xlab='', main="Perm test")
    mtext(expression(Chi^2), side = 1, line = 2)
    abline(v = perm_test$Observed, col = "blue", lty=5)
    curve(dchisq(x, df), add=TRUE, col="green", lwd=2)
}

permutation_test_results <- function(data_control, meta_control, data_treatment, meta_treatment, group_id) {
    r <- data.frame(group_id=character(0), exp_control=numeric(0), exp_treatment=numeric(0), chisq=numeric(0), p=numeric(0), cosine=numeric(0), email_control=character(0), email_treatment=character(0), comment_control=character(0), comment_treatment=character(0), personalized=character(0), device_treatment=character(0), device_control=character(0), aggregated=logical(0))
     ## compute statistics
    t <- permutation_test(data_control, data_treatment)
    r <- r %>% add_row(group_id = group_id, exp_control = meta_control@id, exp_treatment = meta_treatment@id, chisq = t$Observed, p = t$p.value,email_control = meta_control@email, email_treatment = meta_treatment@email, personalized = get_personalization_string_2(meta_control, meta_treatment), device_control = meta_control@device, device_treatment = meta_treatment@device,comment_control = meta_control@comment, comment_treatment = meta_treatment@comment, aggregated=FALSE)
    return(r)
}