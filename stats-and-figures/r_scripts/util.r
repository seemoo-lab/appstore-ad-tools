get_head_of_each_chunk <- function(data, threshhold, head_minutes) {
  data$time_shifted <- shift(data$time, n=1, type='lag', fill=data$time[1])

   ## chunk id construction
    data <- data %>%
        ## first get the time_diff to previous value
        mutate(time_diff = time - time_shifted) %>%
        ## build a boolean vector based on the threshold comparison
        mutate(thresh = time_diff > threshhold)
    ## use cumsum function to increase whenever True is encountered
    data$chunk <- cumsum(data$thresh)

  data_head <- data %>% group_by(chunk) %>% filter(time <= min(time) + 600)

  return(data_head)

}


##iOS

clean_categories_ios <- function(data, game_categories) {
    data <- mutate(data, store_category = replace(store_category, store_category_id %in% game_categories, "Games"))
    return(data)
  }

clean_categories_android <- function(data) {
  data <- mutate(data, store_category = replace(store_category, substr(store_category,1,5) == "GAME_", "GAME"))
  return(data)
}

probe_and_install_packages <- function(packages) {
  lapply(
  packages,
  FUN = function(x) {
    if (!require(x, character.only = TRUE)) {
      install.packages(x, dependencies = TRUE)
      library(x, character.only = TRUE)
    }
  }
)
}

## experiment_metadate class
setClass("experiment_metadata",
         slots = list(
           id = "numeric",
           email = "character",
           comment = "character",
           birth = "POSIXct",
           device = "character",
           treatment = "logical",
           personalized = "logical"
         ))

get_meta_string <- function(meta_control, meta_treatment) {
  return(sprintf("%i - %s (%s - %s - %s)\n%i - %s (%s - %s - %s)",
                 meta_control@id,
                 meta_control@comment,
                 meta_control@email,
                 meta_control@birth,
                 meta_control@device,
                 meta_treatment@id,
                 meta_treatment@comment,
                 meta_treatment@email,
                 meta_treatment@birth,
                 meta_treatment@device))
}
get_exp_string <- function(meta) {
    r <- sprintf("%s%s", meta@id, get_personalization_string(meta))
    return(r)
}

get_personalization_string <- function(meta) {
    if (meta@personalized) {
        r <- "_p"
    } else {
        r <- "_np"
    }
    return(r)
}

get_personalization_string_2 <- function(meta_control, meta_treatment) {
    r <- sprintf("%s%s", get_personalization_string(meta_control), get_personalization_string(meta_treatment))
}
