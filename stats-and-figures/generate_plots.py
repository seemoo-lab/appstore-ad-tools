#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "matplotlib",
#     "pandas",
#     "psycopg",
#     "seaborn",
#     "dotenv",
#     "scikit-learn",
#     "IPython",
# ]
# ///

"""Helper script to generate the plots needed for the paper."""

from functools import reduce
import os
import matplotlib.pyplot as plt
import pandas as pd
import psycopg
import seaborn as sns
from dotenv import load_dotenv
from sklearn.metrics.pairwise import pairwise_distances, cosine_similarity
import numpy as np
from plot_helpers import fetch_run, get_all_with_np, fetch_ids_with_np, spo_to_string, get_all_gids_with_np, get_all
from matplotlib.colors import LogNorm, LinearSegmentedColormap, to_rgba
from matplotlib.patches import Patch
import matplotlib.ticker as ticker
from matplotlib.ticker import FormatStrFormatter, FuncFormatter
from itertools import batched
import os.path
from matplotlib.colors import to_rgba
from matplotlib import font_manager

# cursed workaround for regenerating used categories file
regenerate = False

# colors from https://graphicdesign.stackexchange.com/questions/3682/where-can-i-find-a-large-palette-set-of-contrasting-colors-for-coloring-many-d
colors = ['#023fa5',
 '#7d87b9',
 '#bec1d4',
 '#d6bcc0',
 '#bb7784',
 '#8e063b',
 '#4a6fe3',
 '#8595e1',
 '#b5bbe3',
 '#e6afb9',
 '#e07b91',
 '#d33f6a',
 '#11c638',
 '#8dd593',
 '#c6dec7',
 '#ead3c6',
 '#f0b98d',
 '#ef9708',
 '#0fcfc0',
 '#9cded6',
 '#d5eae7',
 '#f3e1eb',
 '#f6c4e1',
 '#f79cd4']

colors_android = ['#023fa5',
 '#7d87b9',
 '#bec1d4',
 '#d6bcc0',
 '#bb7784',
 '#8e063b',
 '#4a6fe3',
 '#8595e1',
 '#b5bbe3',
 '#e6afb9',
 '#e07b91',
 '#d33f6a',
 '#11c638',
 '#8dd593',
 '#c6dec7',
 '#ead3c6',
 '#f0b98d',
 '#ef9708',
 '#0fcfc0',
 '#9cded6',
 '#d5eae7',
 '#f3e1eb',
 '#f6c4e1',
 '#f79cd4']
import random
random.seed(1873291237)
random.shuffle(colors_android)

graph_color_android = "#c3d5a8"
graph_color_android_darker = "#9db777"
graph_color_ios = "#ffce97"
graph_color_ios_darker = "#e8a961"

## Experiment constants
android_baseline_group_id = "cab5eaba-fda2-488d-a1d8-eaf1ffa3b9b9"
android_finance_group_id = "86afc5ba-a2ce-4f3c-98b0-528ed0a3b4d8"
android_mental_health_group_id = "150a0ac7-4af3-48c3-b9b8-0e7d2e354ee8"
android_shopping_group_id = "1b89b22e-486f-4b22-aac5-e39fa5117b7f"
android_parenting_group_id = "1cf67789-5a77-4a55-8eb1-f7cdf8432599"
android_weight_loss_group_id = "71d822d5-7f72-44ef-853c-34bd42d26983"
android_gambling_group_id = "a7b722de-37f4-46c2-971e-9cf27aeca31d"
android_alcohol_group_id = "2c9c19b8-2ee1-4dc8-9281-c59c0179e52f"
android_gender_group_id = "3bbc0228-16d2-43f9-a36d-b441b710a795"
android_age_group_3 = "41ab440f-7b1f-434a-ac2e-43688fe6c595-0"
android_age_group_2 = "41ab440f-7b1f-434a-ac2e-43688fe6c595-1"
android_age_group_1 = "41ab440f-7b1f-434a-ac2e-43688fe6c595-2"
android_name_group_1 = "d3d9ebaa-52c5-483a-a835-b1771e90ade3-0"
android_name_group_2 = "d3d9ebaa-52c5-483a-a835-b1771e90ade3-1"
android_parenting_repetition_group_id = "1d9f9f59-171e-4369-9e59-02022e7c79d5"
android_weight_loss_repetition_group_id = "805063aa-0fe6-4ad6-b09c-3c528aaf01f1"
android_gambling_repetition_group_id = "07a2eb36-c1de-43b5-a1af-1b19403b25e9"


name_from_gid_lookup_android = {
    "cab5eaba-fda2-488d-a1d8-eaf1ffa3b9b9": "Play Store Baseline",
    "86afc5ba-a2ce-4f3c-98b0-528ed0a3b4d8": "Play Store Finance",
    "150a0ac7-4af3-48c3-b9b8-0e7d2e354ee8": "Play Store Mental Health",
    "1b89b22e-486f-4b22-aac5-e39fa5117b7f": "Play Store Shopping",
    "1cf67789-5a77-4a55-8eb1-f7cdf8432599": "Play Store Parenting",
    "71d822d5-7f72-44ef-853c-34bd42d26983": "Play Store Weight Loss",
    "a7b722de-37f4-46c2-971e-9cf27aeca31d": "Play Store Gambling",
    "2c9c19b8-2ee1-4dc8-9281-c59c0179e52f": "Play Store Sobriety",
    "3bbc0228-16d2-43f9-a36d-b441b710a795": "Play Store Gender - Male (Control) vs. Female",
    "41ab440f-7b1f-434a-ac2e-43688fe6c595-0": "Play Store Age Group 50 (Control) vs. 85",
    "41ab440f-7b1f-434a-ac2e-43688fe6c595-1": "Play Store Age Group 25 (Control) vs. 85",
    "41ab440f-7b1f-434a-ac2e-43688fe6c595-2": "Play Store Age Group 25 (Control) vs. 50",
    "d3d9ebaa-52c5-483a-a835-b1771e90ade3-0": "Play Store Name Group 1 - Chinese Name",
    "d3d9ebaa-52c5-483a-a835-b1771e90ade3-1": "Play Store Name Group 2 - Turkish Name",
    "1d9f9f59-171e-4369-9e59-02022e7c79d5": "Play Store Parenting Repetition",
    "805063aa-0fe6-4ad6-b09c-3c528aaf01f1": "Play Store Weight Loss Repetition",
    "07a2eb36-c1de-43b5-a1af-1b19403b25e9": "Play Store Gambling Repetition"
}

android_account_params = [
    android_gender_group_id,
    android_age_group_1,
    android_age_group_2,
    android_age_group_3,
    android_name_group_1,
    android_name_group_2,
]

android_personas = [
    android_finance_group_id,
    android_mental_health_group_id,
    android_shopping_group_id,
    android_parenting_group_id,
    android_weight_loss_group_id,
    android_gambling_group_id,
    android_alcohol_group_id,
    # android_parenting_repetition_group_id,
    # android_weight_loss_repetition_group_id,
    # android_gambling_repetition_group_id,
]

android_all = [android_baseline_group_id] + android_account_params + android_personas

"""Generated by:
SELECT DISTINCT app_detail.data->>'applicationCategory'
AS store_category
FROM app_detail
WHERE platform = 'android'
ORDER BY store_category ASC;"""
android_categories = [
    'ART_AND_DESIGN',
    'AUTO_AND_VEHICLES',
    'BEAUTY',
    'BOOKS_AND_REFERENCE',
    'BUSINESS',
    'COMICS',
    'COMMUNICATION',
    'DATING',
    'EDUCATION',
    'ENTERTAINMENT',
    'EVENTS',
    'FINANCE',
    'FOOD_AND_DRINK',
    'GAME',
    # 'GAME_ACTION',
    # 'GAME_ADVENTURE',
    # 'GAME_ARCADE',
    # 'GAME_BOARD',
    # 'GAME_CARD',
    # 'GAME_CASUAL',
    # 'GAME_EDUCATIONAL',
    # 'GAME_MUSIC',
    # 'GAME_PUZZLE',
    # 'GAME_RACING',
    # 'GAME_ROLE_PLAYING',
    # 'GAME_SIMULATION',
    # 'GAME_SPORTS',
    # 'GAME_STRATEGY',
    # 'GAME_WORD',
    'HEALTH_AND_FITNESS',
    'HOUSE_AND_HOME',
    'LIFESTYLE',
    'MAPS_AND_NAVIGATION',
    'MEDICAL',
    'MUSIC_AND_AUDIO',
    'NEWS_AND_MAGAZINES',
    'PARENTING',
    'PERSONALIZATION',
    'PHOTOGRAPHY',
    'PRODUCTIVITY',
    'SHOPPING',
    'SOCIAL',
    'SPORTS',
    'TOOLS',
    'TRAVEL_AND_LOCAL',
    'VIDEO_PLAYERS',
    'WEATHER',
]

"""Generated by:
SELECT DISTINCT js->>'id' as id, js->'attributes'->>'name' AS store_category
FROM app_detail, jsonb_array_elements(app_detail.data->'relationships'->'genres'->'data') as js
WHERE platform = 'ios'
ORDER BY store_category ASC;
"""
ios_categories = [
    "Action",
    "Adventure",
    "Board",
    "Books",
    "Business",
    "Card",
    "Casino",
    "Casual",
    "Developer Tools",
    "Education",
    "Entertainment",
    "Family",
    "Finance",
    "Food & Drink",
    "Games",
    "Graphics & Design",
    "Health & Fitness",
    "Lifestyle",
    "Magazines & Newspapers",
    "Medical",
    "Music",
    "Music",
    "Navigation",
    "News",
    "Photo & Video",
    "Productivity",
    "Puzzle",
    "Racing",
    "Reference",
    "Role-Playing",
    "Shopping",
    "Simulation",
    "Social Networking",
    "Sports",
    "Sports",
    "Strategy",
    "Travel",
    "Trivia",
    "Utilities",
    "Weather",
    "Word",
]

ios_shopping_group_id = "D567A879-FF03-42FE-B3A5-FFA135F76189"
ios_finance_group_id = "99C99144-6765-4846-ACAA-376862EA0C2C"
ios_sobriety_group_id = "18E6BD49-02A3-4BA9-9975-4EFCCF5800A1"
ios_parenting_group_id = "046490F0-DE22-4488-A414-7007B77086AA"
ios_casino_group_id = "612F1E8D-A7A6-4473-A1D9-26295921A9AD"
ios_healthcare_group_id = "E48C18AE-4DC8-4C4B-BC70-898A7FFD69E4"
ios_diet_group_id = "EA1BE566-2C12-4ACC-8897-58FC50673913"
ios_gender_group_id = "5A309DE1-29DE-4358-AB77-07A13F1F233E"
ios_age_1_group_id = "9E434362-E669-4F9F-B6E3-D04210300D49-1"
ios_age_2_group_id = "9E434362-E669-4F9F-B6E3-D04210300D49-2"
ios_age_3_group_id = "9E434362-E669-4F9F-B6E3-D04210300D49-3"
ios_name_1_group_id = "60E220A9-44EA-4E9A-8770-639498515F42-1"
ios_name_2_group_id = "60E220A9-44EA-4E9A-8770-639498515F42-2"
ios_shopping_parameter_test_group_id = "2F1A4282-C80D-434D-B68B-6AE0D157FDA3"
ios_repeat_shopping_test = "A1ACE0AB-8FC2-48E2-940E-9DAD75660CEA"
ios_repeat_gender_test = "3EDBD356-B855-4AFE-93CA-02BB353D04DC"
ios_baseline_id = "F6498D66-B5AD-4DF1-9788-22EA06EEF601"

name_from_gid_lookup_ios = {
    "D567A879-FF03-42FE-B3A5-FFA135F76189": "App Store Shopping",
    "99C99144-6765-4846-ACAA-376862EA0C2C": "App Store Finance",
    "18E6BD49-02A3-4BA9-9975-4EFCCF5800A1": "App Store Sobriety",
    "046490F0-DE22-4488-A414-7007B77086AA": "App Store Parenting",
    "612F1E8D-A7A6-4473-A1D9-26295921A9AD": "App Store Casino",
    "E48C18AE-4DC8-4C4B-BC70-898A7FFD69E4": "App Store Healthcare",
    "EA1BE566-2C12-4ACC-8897-58FC50673913": "App Store Weight Loss",
    "5A309DE1-29DE-4358-AB77-07A13F1F233E": "App Store Gender - Male (Control) vs. Female",
    "9E434362-E669-4F9F-B6E3-D04210300D49-1": "App Store Age Group 25 (Control) vs. 50",
    "9E434362-E669-4F9F-B6E3-D04210300D49-2": "App Store Age Group 25 (Control) vs. 85",
    "9E434362-E669-4F9F-B6E3-D04210300D49-3": "App Store Age Group 50 (Control) vs. 85",
    "60E220A9-44EA-4E9A-8770-639498515F42-1": "App Store Name 1 - Chinese Name",
    "60E220A9-44EA-4E9A-8770-639498515F42-2": "App Store Name 2 - Turkish Name ",
    "2F1A4282-C80D-434D-B68B-6AE0D157FDA3": "App Store Shopping Parameter Test",
    "A1ACE0AB-8FC2-48E2-940E-9DAD75660CEA": "App Store Repeat Shopping test",
    "3EDBD356-B855-4AFE-93CA-02BB353D04DC": "App Store Repeat Gender test",
    "F6498D66-B5AD-4DF1-9788-22EA06EEF601": "App Store Baseline",
}

ios_account_params = [
    ios_gender_group_id,
    ios_age_1_group_id,
    ios_age_2_group_id,
    ios_age_3_group_id,
    ios_name_1_group_id,
    ios_name_2_group_id,
]

ios_personas = [
    ios_shopping_group_id,
    ios_finance_group_id,
    ios_parenting_group_id,
    ios_healthcare_group_id,
    ios_diet_group_id,
    ios_casino_group_id,
    ios_sobriety_group_id,
]

ios_all = [ios_baseline_id] + ios_account_params + ios_personas



# fix font embedding (?)
plt.rcParams.update({'pdf.fonttype': 42})
plt.rcParams.update({'ps.fonttype': 42})

## Plotting functions
def jaccard_sim_heatmap(specifier, gids, platform, from_search_page, type, min_val, cur):
    """Plot an aggregated jaccard similarity heatmap for the given group ids."""

    list_of_feature_vectors = []
    for gid in gids:
        for (idx_c, idx_t, idx_c_np, idx_t_np) in fetch_ids_with_np(gid, cur):
            # fetch data
            df_p = fetch_run(idx_c, idx_t, platform, from_search_page, type, cur)
            df_np = fetch_run(idx_c_np, idx_t_np, platform, from_search_page, type, cur)

            if len(df_p) == 0 or len(df_np) == 0:
                print(f"Empty df for {idx_c} {idx_t} {idx_c_np} {idx_t_np} , skipping.")
                continue

            # shape data: we want the mean over all individual groups, so we start by building a list of feature vecs
            freq_table_features = np.array(
                list(
                    pd.concat([df_p, df_np])
                    # convert to frequency table
                    .groupby(
                        [
                            "sub_group_id",
                            "experiment_id",
                            "treatment",
                            "personalized",
                            "label",
                        ]
                    )["label"]
                    .count()
                    .unstack(fill_value=0)
                    .sort_values(["treatment", "personalized"])
                    .itertuples(index=False, name=None)
                ),
                dtype=bool,
            )

            # calculate jaccard sim as 1 - jaccard distance
            jaccard_sim_matrix = 1 - pairwise_distances(freq_table_features, metric="jaccard")
            list_of_feature_vectors.append(jaccard_sim_matrix)


    mean_features = np.mean(list_of_feature_vectors, axis=0)

    labels = ['C/NP', "C/P", "T/NP", "T/P"]
    colors = ['#ecf2e3', graph_color_android_darker] if platform == 'android' else ['#fcf6ef', graph_color_ios_darker]
    positions = [0, 1]
    cmap = LinearSegmentedColormap.from_list('my_colormap', list(zip(positions, colors)))
    ax = sns.heatmap(mean_features,
                     annot=True,
                     annot_kws={"fontsize":14},
                     cmap=cmap,
                     fmt=".2f",
                     cbar=True,
                     vmin=min_val,
                     xticklabels=labels, yticklabels=labels)

    plt.xticks(fontsize=14)
    plt.yticks(fontsize=14)

    # force formatting of legend
    colorbar = ax.collections[0].colorbar
    colorbar.ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.2f}"))

    ax.set_xlabel('Group', fontsize=15, family="serif")
    ax.set_ylabel('Group', fontsize=15, family="serif")
    ax.set_aspect('equal')
    # gen paper related name (could be done smarter but who cares)
    if platform == "android":
        if specifier == "baseline":
            if type == "ad":
                filename = "figure_6_a_baseline_ads"
            else:
                filename = "figure_6_b_baseline_recommendations"
        elif specifier == "account_param_persona":
            if type == 'ad':
                filename = "figure_6_c_account_param_ads"
            else:
                filename = "figure_6_d_account_param_recommendations"
        elif specifier == "interest_persona":
            if type == 'ad':
                filename = "figure_6_e_interest-based_ads"
            else:
                filename = "figure_6_f_interest-based_recommendations"
        else:
            raise RuntimeError("illegal state")
    else:
        if specifier == "baseline":
            if from_search_page:
                filename = "figure_7_a_baseline_ads_search_tab"
            else:
                filename = "figure_7_b_baseline_ads_today_tab"
        elif specifier == "account_param_persona":
            if from_search_page:
                filename = "figure_7_c_account_param_ads_search_tab"
            else:
                filename = "figure_7_d_account_param_ads_today_tab"
        elif specifier == "interest_persona":
            if from_search_page:
                filename = "figure_7_e_interest-based_ads_search_tab"
            else:
                filename = "figure_7_f_interest-based_ads_today_tab"
        else:
            raise RuntimeError("illegal state")

    plt.savefig(f"gen/{filename}.pdf",
                format='pdf', bbox_inches='tight', dpi=300)
    plt.clf()
    plt.close('all') # try to prevent memleak?


def jaccard_sim_heatmap_cross_device(specifier, gids, platform, from_search_page, type, min_val, cur):
    """Plot an cross device aggregated jaccard similarity heatmap for the given group ids."""

    for gid in gids:
        for characteristics in ["category", "label"]:
            df = get_all(gid, platform, from_search_page, type, cur)

            comment = df.iloc[0]["comment"]

            # convert to frequency table
            df = df.groupby(["experiment_id", "treatment", "personalized", "device_serial", "sub_group_id", characteristics])[characteristics].count().unstack(fill_value=0).sort_values(["device_serial", "treatment", "sub_group_id"])
            feature_vectors = list(df.itertuples(index=False, name=None))
            # display(df)

            # calculate cosine sim
            cos_sim_matrix = cosine_similarity(X=feature_vectors)

            # get the labels
            labels = [f'{l[0]} - {"T" if l[1] else "C"}/{"P" if l[2] else "NP"} {l[3]}' for l in df.index]

            sns.heatmap(np.array(cos_sim_matrix), annot=True, annot_kws={"fontsize":8},
                        cmap='coolwarm', fmt=".3f", cbar=True, xticklabels=labels, yticklabels=labels)

            plt.title(f'Cosine Similarity Heatmap - In whole group "{comment}" for {characteristics}')
            plt.xlabel('Feature Vector Index')
            plt.ylabel('Feature Vector Index')

            plt.savefig(f"gen/cross_device_{platform}_{specifier}_jaccard_{type}_{spo_to_string(from_search_page)}.pdf",
                        format='pdf', bbox_inches='tight', dpi=300)
            plt.clf()
            plt.close('all') # try to prevent memleak?

def label_freq_heatmap(gids, platform, search_page_option, type, cur):
    df = get_all_gids_with_np(gids, platform, search_page_option, type, cur)
    df = df.groupby(["label", "experiment_id"])["label"].count().unstack(fill_value=0)

    # get the sums to sort by
    df['sum']= df.sum(axis=1, numeric_only=True)

    # sort df
    df = df.sort_values(by=["sum"], ascending=False).drop(columns=['sum'])

    fig, ax = plt.subplots(figsize=(30, 10))
    sns.heatmap(df, annot=False, cmap='coolwarm', cbar=True, norm=LogNorm())
    ax.set_aspect("auto")
    ax.set(xticklabels=[])
    ax.set(yticklabels=[])

    plt.savefig(f"gen/{platform}_label_freq_heatmap_{type}_{spo_to_string(search_page_option)}.pdf",
                format='pdf', bbox_inches='tight', dpi=300)
    plt.clf()
    plt.close('all') # try to prevent memleak?


def category_distribution_stacked_bar_plot(gid, platform, cur):
    """Generate stacked bar plots."""

    def preprocess(df):
        # skip gambling personas, games might be relevant
        # if gid not in [android_gambling_group_id]:
        df.category = df.category.str.replace('GAME_.*','GAME', regex=True)

        # group by subgroup, treatment, and personalized, experiment_id, and count categories (betwenn 0-1, then upscale to percent)
        groups = df.groupby(["type", "sub_group_id", "treatment", "personalized", "experiment_id"])["category"].value_counts(normalize=True) * 100

        if platform == 'android':
            expanded = groups.unstack(fill_value=0).sort_values(["treatment", "personalized", "experiment_id"],
                                                                ascending=[True, False, True])
        else:
            expanded = groups.unstack(fill_value=0).sort_values(["sub_group_id", "personalized", "treatment", "experiment_id"],
                                                                ascending=[True, False, True, True])

        # extract type from index as normal column -> we need that to filter later
        expanded = expanded.reset_index(level='type')

        # flatten mutli index, make it human readable
        expanded.index = [f'{"T" if treatment else "C"}/{"P" if personalized else "NP"}'
                          # matches the groupby definition above
                          for (sid, treatment, personalized, experiment_id) in expanded.index]
        expanded = expanded.reset_index(names=["run"])

        # group together consistently very small groups by threshold
        threshold = 5
        # Find columns where *all* values are below the threshold
        small_cols = [col for col in expanded.columns if col != "run" and col != "type" and (expanded[col] < threshold).all()]
        # Sum them into an "Other" column
        expanded['Other'] = expanded[small_cols].sum(axis=1)
        # Drop the small columns
        expanded = expanded.drop(columns=small_cols)

        return expanded

    # get all data with np for this group and pre-process
    if platform == 'android':
        df_ad = preprocess(get_all_with_np(gid, platform, None, 'ad', cur))
        df_suggestion = preprocess(get_all_with_np(gid, platform, None, 'suggestion', cur))
    else:
        # for ios, we want to compare search and today page.
        df_ad = preprocess(get_all_with_np(gid, platform, True, 'ad', cur)) # this is actually the search page
        df_suggestion = preprocess(get_all_with_np(gid, platform, False, 'ad', cur)) # this is the today page

    if df_ad.empty or df_suggestion.empty:
        print("Warning: DF is empty, skipping")
        return False

    # Create main figure with two horizontal subfigures
    fig = plt.figure(figsize=(10, 3.9))
    subfigs = fig.subfigures(1, 2, width_ratios=[1, 1])

    # setup consistent colormapping
    platform_cats = android_categories if platform == 'android' else ios_categories

    # experiment with gambling where gaming cats make a difference
    # if gid in [android_gambling_group_id]:
    #     platform_cats += [
    #         'GAME_ACTION',
    #         'GAME_ADVENTURE',
    #         'GAME_ARCADE',
    #         'GAME_BOARD',
    #         'GAME_CARD',
    #         'GAME_CASUAL',
    #         'GAME_EDUCATIONAL',
    #         'GAME_MUSIC',
    #         'GAME_PUZZLE',
    #         'GAME_RACING',
    #         'GAME_ROLE_PLAYING',
    #         'GAME_SIMULATION',
    #         'GAME_SPORTS',
    #         'GAME_STRATEGY',
    #         'GAME_WORD'
    #     ]

    if not os.path.isfile(f"used_cats_{platform}.txt"):
        global regenerate
        regenerate = True
        print("********** Info: Generating `used_cats` file.")

    if not regenerate:
        # sort to get determinism, else set order is not fixed
        categories = sorted(list(set(map(str.strip, open(f"used_cats_{platform}.txt").readlines())).union({"Other"})))
        color_map = dict(zip(categories, colors if platform == "ios" else colors_android))

        if platform == "android":
            game_switch_target = "PRODUCTIVITY"
            color_map[game_switch_target], color_map["GAME"] = color_map["GAME"], color_map[game_switch_target]
    else:
        categories = sorted(set(platform_cats) | {'Other'})
        cmap = sns.color_palette("husl", len(categories))
        color_map = dict(zip(categories, cmap))



    # we do not want to include all categories, only those used
    # this is later needed to generate the correct legend
    used_categories = sorted(set(df_ad.columns).union(df_suggestion.columns) - {'run', 'type', 'Other'}) # we add Other later

    if regenerate:
        open(f"used_cats_{platform}.txt", "a").writelines(map(lambda x: x + "\n", used_categories))

    # create the subfigures
    for i, df in enumerate([df_ad, df_suggestion]):
        ax = subfigs[i].subplots()

        # fix order
        df = df.reindex(sorted(df.columns, reverse=True), axis=1)
        # put 'Other' at the end
        other_col = df.pop('Other')
        df.insert(-0, 'Other', other_col)

        # plot this subplot
        df.plot(
            x="run",
            kind='bar',
            stacked=True,
            width=0.9,
            color=[color_map[cat] for cat in [c for c in df.columns if c not in {'run', 'type'}]],
            ax=ax
        )

        # label (only for the left graph)
        if i == 0:
            ax.set_ylabel("Category Fraction [%]", family="serif")

        if platform == 'android':
            ax.set_xlabel("Ads" if i == 0 else "Recommendations", family="serif")
        else:
            # for ios, we have search page and today page
            ax.set_xlabel("Search Tab" if i == 0 else "Today Tab", family="serif")

        # move y axis to the right for second graph
        if i == 1:
            ax.yaxis.set_ticks_position('right')        # move ticks
            ax.yaxis.set_label_position('right')        # move label
            ax.spines['right'].set_position(('outward', 0))  # show the right spine
            ax.spines['right'].set_visible(True)        # make sure it's visible
            ax.spines['left'].set_visible(False)        # hide the left spine

        ax.tick_params(axis='both', which='major', labelsize=8)
        ax.tick_params(axis='both', which='minor', labelsize=6)

        # remove frame border
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)

        # add percentages
        for container in ax.containers:
            for rect in container:
                height = rect.get_height()
                label_col = '#424242'
                if platform == "android":
                    if rect.get_fc() in [to_rgba(color_map["ENTERTAINMENT"]),
                                         to_rgba(color_map["MUSIC_AND_AUDIO"]),
                                         to_rgba(color_map["Other"]),
                                         to_rgba(color_map["TRAVEL_AND_LOCAL"]),
                                         to_rgba(color_map["HEALTH_AND_FITNESS"])]:
                        label_col = '#ededed'
                else:
                    if rect.get_fc() in [to_rgba(color_map["Games"]),
                                         to_rgba(color_map["Shopping"]),
                                         to_rgba(color_map["Business"]),
                                         to_rgba(color_map["Education"]),
                                         to_rgba(color_map["Health & Fitness"]),
                                         to_rgba(color_map["News"])]:
                        label_col = '#ededed'

                if height == 0:
                    continue  # Skip zero-height bars
                ax.text(
                    rect.get_x() + rect.get_width() / 2,
                    rect.get_y() + height / 2,
                    f"{height:.1f}",   # Directly use the height as value
                    ha='center',
                    va='center',
                    fontsize=5.5,
                    color=label_col
                )
        # remove legend
        ax.get_legend().remove()

    # generate globally consistent legend. 'Other' has to be the topmost item.
    legend_handles = [Patch(color=color_map[cat], label=cat) for cat in used_categories + ['Other']]
    fig.legend(legend_handles,
               map(lambda c: c.title().replace("_And_", " & "), used_categories + ['Other']),
               loc='center',
               prop={'size': 7},
               frameon=False,
               bbox_to_anchor=(0.507, 0.5))

    # construct paper filename
    figurename_from_gid_lookup_android = {
        "cab5eaba-fda2-488d-a1d8-eaf1ffa3b9b9"   : "figure_8_a_Play_Store_Baseline",
        "86afc5ba-a2ce-4f3c-98b0-528ed0a3b4d8"   : "figure_8_i_Play_Store_Finance",
        "150a0ac7-4af3-48c3-b9b8-0e7d2e354ee8"   : "figure_8_k_Play_Store_Mental_Health",
        "1b89b22e-486f-4b22-aac5-e39fa5117b7f"   : "figure_8_h_Play_Store_Shopping",
        "1cf67789-5a77-4a55-8eb1-f7cdf8432599"   : "figure_8_j_Play_Store_Parenting",
        "71d822d5-7f72-44ef-853c-34bd42d26983"   : "figure_8_l_Play_Store_Weight_Loss",
        "a7b722de-37f4-46c2-971e-9cf27aeca31d"   : "figure_8_m_Play_Store_Gambling",
        "2c9c19b8-2ee1-4dc8-9281-c59c0179e52f"   : "figure_8_n_Play_Store_Sobriety",
        "3bbc0228-16d2-43f9-a36d-b441b710a795"   : "figure_8_b_Play_Store_Gender_-_Male_(Control)_vs_Female",
        "41ab440f-7b1f-434a-ac2e-43688fe6c595-0" : "figure_8_e_Play_Store_Age_Group_50_(Control)_vs_85",
        "41ab440f-7b1f-434a-ac2e-43688fe6c595-1" : "figure_8_d_Play_Store_Age_Group_25_(Control)_vs_85",
        "41ab440f-7b1f-434a-ac2e-43688fe6c595-2" : "figure_8_c_Play_Store_Age_Group_25_(Control)_vs_50",
        "d3d9ebaa-52c5-483a-a835-b1771e90ade3-0" : "figure_8_f_Play_Store_Name_Group_1_-_Chinese_Name",
        "d3d9ebaa-52c5-483a-a835-b1771e90ade3-1" : "figure_8_g_Play_Store_Name_Group_2_-_Turkish_Name",
    }

    figurename_from_gid_lookup_ios = {
        "D567A879-FF03-42FE-B3A5-FFA135F76189"   : "figure_9_h_App_Store_Shopping",
        "99C99144-6765-4846-ACAA-376862EA0C2C"   : "figure_9_i_App_Store_Finance",
        "18E6BD49-02A3-4BA9-9975-4EFCCF5800A1"   : "figure_9_n_App_Store_Sobriety",
        "046490F0-DE22-4488-A414-7007B77086AA"   : "figure_9_j_App_Store_Parenting",
        "612F1E8D-A7A6-4473-A1D9-26295921A9AD"   : "figure_9_m_App_Store_Casino",
        "E48C18AE-4DC8-4C4B-BC70-898A7FFD69E4"   : "figure_9_k_App_Store_Healthcare",
        "EA1BE566-2C12-4ACC-8897-58FC50673913"   : "figure_9_l_App_Store_Weight_Loss",
        "5A309DE1-29DE-4358-AB77-07A13F1F233E"   : "figure_9_b_App_Store_Gender_-_Male_(Control)_vs_Female",
        "9E434362-E669-4F9F-B6E3-D04210300D49-1" : "figure_9_c_App_Store_Age_Group_25_(Control)_vs_50",
        "9E434362-E669-4F9F-B6E3-D04210300D49-2" : "figure_9_d_App_Store_Age_Group_25_(Control)_vs_85",
        "9E434362-E669-4F9F-B6E3-D04210300D49-3" : "figure_9_e_App_Store_Age_Group_50_(Control)_vs_85",
        "60E220A9-44EA-4E9A-8770-639498515F42-1" : "figure_9_f_App_Store_Name_1_-_Chinese_Name",
        "60E220A9-44EA-4E9A-8770-639498515F42-2" : "figure_9_g_App_Store_Name_2_-_Turkish_Name_",
        "F6498D66-B5AD-4DF1-9788-22EA06EEF601"   : "figure_9_a_App_Store_Baseline",
    }
    if platform == "android":
        filename = figurename_from_gid_lookup_android[gid]
    else:
        filename = figurename_from_gid_lookup_ios[gid]

    # write pdf file with the combined figure
    fig.savefig(f"gen/{filename}.pdf",
                format='pdf', bbox_inches='tight', dpi=300)
    plt.clf()
    plt.close('all') # try to prevent memleak?
    return True


def stacked_bar_plot_selection(cur):
    """Generate the stacked bar plot in the main body of the paper (only 4 bars android / ios each.)"""

    def preprocess(df, spo):
        df.category = df.category.str.replace('GAME_.*','GAME', regex=True)

        # group by subgroup, treatment, and personalized, experiment_id, and count categories (betwenn 0-1, then upscale to percent)
        groups = df.groupby(["type", "sub_group_id", "treatment", "personalized", "experiment_id"])["category"].value_counts(normalize=True) * 100


        expanded = groups.unstack(fill_value=0).sort_values(["sub_group_id", "personalized", "treatment", "experiment_id"],
                                                                ascending=[True, False, True, True])

        # flatten mutli index, make it human readable
        expanded.index = [f'{"T" if treatment else "C"}/{"P" if personalized else "NP"}'
                          # matches the groupby definition above
                          for (typ, sid, treatment, personalized, experiment_id) in expanded.index]
        expanded = expanded.reset_index(names=["run"])

        # group together consistently very small groups by threshold
        threshold = 5
        # Find columns where *all* values are below the threshold
        small_cols = [col for col in expanded.columns if col != "run" and (expanded[col] < threshold).all()]
        # Sum them into an "Other" column
        expanded['Other'] = expanded[small_cols].sum(axis=1)
        # Drop the small columns
        expanded = expanded.drop(columns=small_cols)

        return expanded

    # fetch required data
    android_data = [
        preprocess(pd.concat([
            fetch_run(805, 804, 'android', None, 'ad', cur),
            fetch_run(806, 807, 'android', None, 'ad', cur),
        ]), None),
        preprocess(pd.concat([
            fetch_run(805, 804, 'android', None, 'suggestion', cur),
            fetch_run(806, 807, 'android', None, 'suggestion', cur)
        ]), None)
    ]
    df_android = pd.concat(android_data)

    ios_data = [
        preprocess(
            pd.concat([
                fetch_run(672, 671, 'ios', True, 'ad', cur),  # ads, personalized
                fetch_run(673, 674, 'ios', True, 'ad', cur),  # ads, non-personalized
            ]),
            True # search page
        ),
        preprocess(
            pd.concat([
                fetch_run(672, 671, 'ios', False, 'ad', cur),
                fetch_run(673, 674, 'ios', False, 'ad', cur),
            ]),
            False # today page
        )
    ]
    df_ios = pd.concat(ios_data)

    # Create main figure with two horizontal subfigures
    fig = plt.figure(figsize=(10, 3.5))
    subfigs = fig.subfigures(1, 2, width_ratios=[1, 1], wspace=-0.05)

    # # we do not want to include all categories, only those used
    # # this is later needed to generate the correct legend
    used_categories_and = sorted(set(df_android.columns) - {'run', 'Other'}) # we add Other later
    used_categories_ios = sorted(set(df_ios.columns) - {'run', 'Other'}) # we add Other later

    # create the subfigures
    for i, df in enumerate([df_android, df_ios]):

        # setup consistent colormapping (we have different categories, so its fine to do it for the subplot)
        used_categories = used_categories_and if i == 0 else used_categories_ios
        categories = sorted(set(used_categories) | {'Other'})

        color_map = dict(zip(categories, colors))

        # fix order
        df = df.reindex(sorted(df.columns, reverse=True), axis=1)
        # put 'Other' at the end
        other_col = df.pop('Other')
        df.insert(-0, 'Other', other_col)

        # fix shopping to color
        # if i == 0:
        #     color_map["SHOPPING"] = (0, 0, 0)
        # else:
        #     color_map["Shopping"] = (0, 0, 0)

        ax = subfigs[i].subplots()

        # plot this subplot
        df.plot(
            x="run",
            kind='bar',
            stacked=True,
            width=0.9,
            ax=ax,
            color=[color_map[cat] for cat in [c for c in df.columns if c not in {'run', 'type'}]],
        )

        # label (only for the left graph)
        if i == 0:
            ax.set_ylabel("Category Fraction [%]", family="serif")

        if i == 0:
            ax.set_xlabel("(a) Play Store", labelpad=20, fontsize=12, family="serif", weight='bold')
        else:
            ax.set_xlabel("(b) App Store", labelpad=20, fontsize=12, family="serif", weight='bold')

        # move y axis to the right for second graph
        if i == 1:
            ax.yaxis.set_ticks_position('left')        # move ticks
            ax.yaxis.set_label_position('left')        # move label
            ax.spines['right'].set_position(('outward', 0))  # show the right spine
            ax.spines['right'].set_visible(True)        # make sure it's visible
            ax.spines['left'].set_visible(False)        # hide the left spine
        elif i == 0:
            ax.yaxis.set_ticks_position('right')        # move ticks
            ax.yaxis.set_label_position('right')        # move label

        ax.tick_params(axis='both', which='major', labelsize=8)
        ax.tick_params(axis='both', which='minor', labelsize=6)

        # add group ticks
        ax_group = ax.twiny()
        ax_group.spines["bottom"].set_position(("axes", -0.142))
        ax_group.tick_params('both', length=0, width=0, which='minor')
        ax_group.tick_params('both', direction='in', which='major')
        ax_group.xaxis.set_ticks_position("bottom")
        ax_group.xaxis.set_label_position("bottom")
        ax_group.set_xticks([0.0, 0.5, 1.0])
        ax_group.xaxis.set_major_formatter(ticker.NullFormatter())
        ax_group.xaxis.set_minor_locator(ticker.FixedLocator([0.25, 0.75]))
        ax_group.xaxis.set_minor_formatter(ticker.FixedFormatter(['Ads', 'Recommendations'] if i == 0 else ["Search Tab", "Today Tab"]))

        font_properties = font_manager.FontProperties(family='serif')

        # Set the font for minor tick labels
        for label in ax_group.get_xticklabels(minor=True):
            label.set_fontproperties(font_properties)

        # remove frame border
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax_group.spines['top'].set_visible(False)
        ax_group.spines['right'].set_visible(False)
        ax_group.spines['left'].set_visible(False)

        # add percentages
        for container in ax.containers:
            for rect in container:
                height = rect.get_height()
                label_col = '#ededed'
                if i == 0:
                    if rect.get_fc() in [to_rgba(color_map["PRODUCTIVITY"]),
                                         to_rgba(color_map["FOOD_AND_DRINK"]),
                                         to_rgba(color_map["Other"]),
                                         to_rgba(color_map["TRAVEL_AND_LOCAL"]),
                                         to_rgba(color_map["FINANCE"])]:
                        label_col = '#424242'
                else:
                    if rect.get_fc() in [#to_rgba(color_map["Other"]),
                                         #to_rgba(color_map["Shopping"]),
                                         #to_rgba(color_map["Business"]),
                                         to_rgba(color_map["Photo & Video"]),
                                         to_rgba(color_map["Entertainment"]),
                                          to_rgba(color_map["Finance"])
                                         ]:
                        label_col = '#424242'

                if height == 0:
                    continue  # Skip zero-height bars
                if height < 5:
                    continue # skip small bars for this excerpt
                ax.text(
                    rect.get_x() + rect.get_width() / 2,
                    rect.get_y() + height / 2,
                    f"{height:.1f}",   # Directly use the height as value
                    ha='center',
                    va='center',
                    fontsize=8,
                    color=label_col
                )
        # remove legend
        ax.get_legend().remove()

        # generate globally consistent legend. 'Other' has to be the topmost item.
        legend_handles = [Patch(color=color_map[cat], label=cat) for cat in used_categories + ['Other']]
        fig.legend(legend_handles,
                   map(lambda c: c.title().replace("_And_", " & "), used_categories + ['Other']),
                   loc='center',
                   prop={'size': 7},
                   frameon=False,
                   bbox_to_anchor=(0.01, 0.5) if i == 0 else (1.0, 0.5),
                   markerfirst = False if i == 0 else True)

    # write pdf file with the combined figure
    fig.savefig("gen/figure_4.pdf",
                format='pdf', bbox_inches='tight', dpi=300)
    plt.clf()
    plt.close('all') # try to prevent memleak?
    return True


def app_name_flamegraph(gids, platform, from_search_page, type, cur, x_nth, y_nth):
    """Plot app name 'flamegraph'."""

    df_org = get_all_gids_with_np(gids, platform, from_search_page, type, cur)
    df = df_org.groupby(["label", "experiment_id"])["label"].count().unstack(fill_value=0)

    original_columns = df.columns

    # get the sums to sort by
    df['n_total']= df.sum(axis=1, numeric_only=True)
    df = df.sort_values(by=["n_total"], ascending=False)
    df = df.drop(columns=["n_total"])

    # get rid of app names as index (we don't need them anymore, so drop)
    df = df.reset_index(drop=True)

    # normalize experiment ids
    df = df.rename(columns={exid: normalized_exid for (exid, normalized_exid) in zip(df.columns, range(len(df.columns)))})

    # every nth row
    df = df.iloc[::x_nth]

    # every nth column (only works since we have no "additional column" here)
    df = df[df.columns[::y_nth]]

    # filter out zero columns
    df = df[~(df == 0).all(axis=1)]

    # we have some outliers that mess up the automatic scale, so fix it to usual max
    vmin = 0
    if platform == 'android':
        vmax = 18 # 18 is the usual max
    else:
        vmax = df.max().max()

    ## plotting starts here (transformations should be done above)
    # prepare colour map to fix vmin to zero_color
    zero_color = '#424444'
    base_cmap = sns.light_palette(graph_color_android if platform == "android" else graph_color_ios, as_cmap=True)
    n_colors = 256
    viridis_colors = base_cmap(np.linspace(0, 1, n_colors - 1))

    # set our zero color as zero
    new_colors = np.vstack((np.array([to_rgba(zero_color)]), viridis_colors))

    # Create the new colormap
    new_cmap = LinearSegmentedColormap.from_list("black_viridis", new_colors)

    # plot heatmap
    figsize_old = plt.rcParams['figure.figsize']
    # plt.rcParams['figure.figsize'] = [.1 * df.shape[1], .1 * df.shape[0]]
    plt.rcParams['figure.figsize'] = [5, 4]
    ax = sns.heatmap(df,
                     annot=False, cmap=new_cmap,
                     cbar=True,
                     vmin=0, vmax=vmax,
                     cbar_kws={"shrink": 0.8}
                     )
    # ax.set_aspect('equal')

    # define fontsizes
    axis_fontsize = 13
    plt.xlabel('Measurement', fontsize=axis_fontsize, family="serif")
    plt.ylabel('Ad for unique app' if type == 'ad' else 'Recommendation for unique app',
               fontsize=axis_fontsize, family="serif")

    # we need to do this manually, else seaborn will hide them due to low figure size
    # ax.set_yticks(range(len(df.index)))
    # ax.set_yticklabels(df.index)
    ticks_fontsize = 9
    plt.yticks(rotation=0, fontsize=ticks_fontsize)
    plt.xticks(rotation=90, fontsize=ticks_fontsize)


    # set tick fontsize of cbar
    cbar = ax.collections[0].colorbar
    cbar.ax.tick_params(labelsize=6)

    # force discrete ticks
    cbar.ax.yaxis.set_major_formatter(FormatStrFormatter('%d'))
    cbar.set_ticks(np.arange(0, vmax + 1))

    plt.tight_layout(pad=0,rect=(0, 0, 1.05, 1))
    # construct paper-related filename
    if platform == "android":
        if type == "ad":
            filename = "figure_5_a_play_store_ads"
        else:
            filename = "figure_5_b_play_store_recommendations"
    else:
        if from_search_page:
            filename = "figure_5_c_app_store_search_tab"
        else:
            filename = "figure_5_d_app_store_today_tab"

    plt.savefig(f"gen/{filename}.pdf",
                format='pdf', # bbox_inches='tight',
                dpi=100)
    plt.clf()
    plt.rcParams['figure.figsize'] = figsize_old
    plt.close('all') # try to prevent memleak


def app_name_flamegraph_full(gids, platform, from_search_page, type, cur):
    """Plot app name 'flamegraph'."""

    df_org = get_all_gids_with_np(gids, platform, from_search_page, type, cur)
    df = df_org.groupby(["label", "experiment_id"])["label"].count().unstack(fill_value=0)

    # get the sums to sort by
    df['n_total']= df.sum(axis=1, numeric_only=True)
    df = df.sort_values(by=["n_total"], ascending=False)
    df = df.drop(columns=["n_total"])

    # get rid of app names as index (we don't need them anymore, so drop)
    df = df.reset_index(drop=True)

    # normalize experiment ids
    df = df.rename(columns={exid: normalized_exid for (exid, normalized_exid) in zip(df.columns, range(len(df.columns)))})

    # we have some outliers that mess up the automatic scale, so fix it to usual max
    vmin = 0
    if platform == 'android':
        vmax = 18 # 18 is the usual max
    else:
        vmax = df.max().max()

    ## plotting starts here (transformations should be done above)
    # prepare colour map to fix vmin to zero_color
    zero_color = '#424444'
    base_cmap = sns.light_palette(graph_color_android if platform == "android" else graph_color_ios, as_cmap=True)
    n_colors = 256
    viridis_colors = base_cmap(np.linspace(0, 1, n_colors - 1))

    # set our zero color as zero
    new_colors = np.vstack((np.array([to_rgba(zero_color)]), viridis_colors))

    # Create the new colormap
    new_cmap = LinearSegmentedColormap.from_list("black_viridis", new_colors)

    # plot heatmap
    figsize_old = plt.rcParams['figure.figsize']
    plt.rcParams['figure.figsize'] = [.1 * df.shape[1], .1 * df.shape[0]]
    ax = sns.heatmap(df,
                     annot=False, cmap=new_cmap,
                     cbar=True,
                     vmin=0, vmax=vmax,
                     cbar_kws={"shrink": 0.8}
                     )
    ax.set_aspect('equal')

    # define fontsizes
    axis_fontsize = 12
    plt.xlabel('Measurement', fontsize=axis_fontsize)
    plt.ylabel('App', fontsize=axis_fontsize)

    # we need to do this manually, else seaborn will hide them due to low figure size
    ax.set_yticks(range(len(df.index)))
    ax.set_yticklabels(df.index)
    plt.yticks(fontsize=5)
    plt.xticks(rotation=90, fontsize=5)


    # set tick fontsize of cbar
    cbar = ax.collections[0].colorbar
    cbar.ax.tick_params(labelsize=6)

    # force discrete ticks
    cbar.ax.yaxis.set_major_formatter(FormatStrFormatter('%d'))
    cbar.set_ticks(np.arange(0, vmax + 1))

    plt.savefig(f"gen/{platform}_{type}_app_name_flamegraph_{spo_to_string(from_search_page)}_full.png",
                format='png', bbox_inches='tight', dpi=100)
    plt.clf()
    plt.rcParams['figure.figsize'] = figsize_old
    plt.close('all') # try to prevent memleak


def generate_latex_figure_stacking_bar_plot_android(subgraphs):
    """Generates LaTex code for the stacking bar plot figure."""

    template_figure = r"""
    \begin{figure*}[h]
    % make it clearer to which subfigure the caption refers to
    \captionsetup[subfigure]{aboveskip=1pt}
    \captionsetup[subfigure]{belowskip=1em}
    \ContinuedFloat
    \centering
    SUBFIGURES
    \vspace{-1em} % undo effects of belowskip above
    \caption{Category distribution of all Play Store measurements before and after deactivating personalized ads (C~=~Control, T~=~Treatment, P~=~Personalized, NP~=~Non-Personalized). ``Other'' captures all categories that are consistently below 5\%.}
    LABEL
    \vspace{-1em} % undo effects of belowskip above
    \end{figure*}%
    """

    template_subfigure = r"""
    \begin{subfigure}{\textwidth}
      \includegraphics[width=\textwidth]{PATH}
      \vspace{-2em}
      \caption{CAPTION}
      \label{fig:PATH}
    \end{subfigure}
    """

    def apply_template(subgraph):
        gid, path = subgraph
        return template_subfigure.replace("PATH", path).replace("CAPTION",
                                                                name_from_gid_lookup_android[gid])

    with open("gen/appendix_figure_android_stacking_barplot.tex", "w") as f:
        # prepare subfigure list. We want 3 per page, then continue the float on the next page
        figures = [
            template_figure.replace("SUBFIGURES", "\\hfill\n\\vspace{-2em}".join(map(apply_template, batch)))
            for batch in batched(subgraphs, n=3)
        ]

        f.write("\n".join(figures).replace("\\ContinuedFloat\n", "", count=1).replace("LABEL", "\\label{fig:category_distrib_stacked_bar_android}", count=1).replace("LABEL", ""))

def generate_latex_figure_stacking_bar_plot_ios(subgraphs):
    """Generates LaTex code for the stacking bar plot figure."""

    template_figure = r"""
    \begin{figure*}[h]
    % make it clearer to which subfigure the caption refers to
    \captionsetup[subfigure]{aboveskip=1pt}
    \captionsetup[subfigure]{belowskip=1em}
    \ContinuedFloat
    \centering
    SUBFIGURES
    \vspace{-1em} % undo effects of belowskip above
    \caption{Category distribution of all App Store measurements before and after deactivating personalized ads (C~=~Control, T~=~Treatment, P~=~Personalized, NP~=~Non-Personalized). ``Other'' captures all categories that are consistently below 5\%.}
    LABEL
    \vspace{-1em} % undo effects of belowskip above
    \end{figure*}%
    """

    template_subfigure = r"""
    \begin{subfigure}{\textwidth}
      \includegraphics[width=\textwidth]{PATH}
      \vspace{-2em}
      \caption{CAPTION}
      \label{fig:PATH}
    \end{subfigure}
    """

    def apply_template(subgraph):
        gid, path = subgraph
        return template_subfigure.replace("PATH", path).replace("CAPTION",
                                                                name_from_gid_lookup_ios[gid])

    with open("gen/appendix_figure_ios_stacking_barplot.tex", "w") as f:
        # prepare subfigure list. We want 3 per page, then continue the float on the next page
        figures = [
            template_figure.replace("SUBFIGURES", "\\hfill\n\\vspace{-2em}".join(map(apply_template, batch)))
            for batch in batched(subgraphs, n=3)
        ]

        f.write("\n".join(figures).replace("\\ContinuedFloat\n", "", count=1).replace("LABEL", "\\label{fig:category_distrib_stacked_bar_ios}", count=1).replace("LABEL", ""))

def gen_unique_app_table(gids, platform, search_page_option, cur):

    ads = []
    suggestions = []

    for type in ["ad", "suggestion"]:
        # get all ads / all suggestions
        df = get_all_gids_with_np(gids, platform, search_page_option, type, cur)

        # to collect all the label sets
        sets = {}

        #t this part differs for ads vs suggestions and on platforms
        if platform == 'android':
            if type == 'ad':
                # generate groupings (sepearted personalized vs. np)
                groups = ['group_id', 'treatment', 'personalized']
                        # generate groupings
                tuples = list(df.groupby(groups)['label'].unique().reset_index().itertuples(name=None, index=False))

                # build all sets
                for group_id, t, p, labels in tuples:
                    sets[(group_id, t, p)] = set(labels)

                # build set differences
                for group_id, t, p, labels in tuples:
                    target_set = sets[(group_id, t, p)]

                    whole_set = reduce(set.union, [sets[k] for k in filter(lambda x: x != (group_id, t, p), sets.keys())])

                    unique_ads = target_set - whole_set

                    # get the runs where these ads appear in
                    runs = ', '.join(
                        [
                            (f'{{\\footnotesize \\emph{{{l}}} ({len(list(df.loc[df["label"] == l]["experiment_id"].drop_duplicates()))})}}'
                             .replace('&', '\\&')
                             .replace('_', '\\_')
                             .encode('ascii',errors='ignore')
                             .decode('ascii'))
                            for l in unique_ads
                        ]
                    )
                    if unique_ads:
                        ads.append(f'{group_id} & {t} & {p} & {runs}\\\\\n')

            elif type == 'suggestion':
                groups = ['group_id', 'treatment']
                        # generate groupings
                tuples = list(df.groupby(groups)['label'].unique().reset_index().itertuples(name=None, index=False))

                # build all sets
                for group_id, t, labels in tuples:
                    sets[(group_id, t)] = set(labels)

                # build set differences
                for group_id, t, labels in tuples:
                    target_set = sets[(group_id, t)]

                    whole_set = reduce(set.union, [sets[k] for k in filter(lambda x: x != (group_id, t), sets.keys())])

                    unique_ads = target_set - whole_set

                    # get the runs where these ads appear in
                    runs = ', '.join(
                        [
                            (f'\\emph{{{l}}} ({len(list(df.loc[df["label"] == l]["experiment_id"].drop_duplicates()))})'
                             .replace('&', '\\&')
                             .replace('_', '\\_')
                             .encode('ascii',errors='ignore')
                             .decode('ascii'))
                            for l in unique_ads
                        ]
                    )
                    if unique_ads:
                        suggestions.append(f'{group_id} &  {t} & & {runs}\\\\\n')
                    else:
                        print(f"No unique ads in {group_id} / {t}.")
            else:
                raise RuntimeError("Illegal state.")
        else:
            raise NotImplementedError("iOS part not implemented.")

    # build table
    table_template =( r"""
    \begin{center}
    \tablehead{
    Group & Treat. & Pers. & Ads / Recommendation (frequency) \\
    \midrule
    }
    \tablecaption{PLACEHOLDER_CAPTION}
    \begin{supertabular*}{ c | c c | p{0.5\textwidth} }
    PLACEHOLDER_ADS
    \midrule
    PLACEHOLDER_SUGGESTIONS
    \end{supertabular*}
    \end{center}
    """
    .replace("PLACEHOLDER_CAPTION", f"Unique ads/recommendations on {platform} between different groups. For recommendations, P and NP groups are merged. Numbers in parenthesis show in how many sub-experiments these ads occurred. Combinations without unique are omitted.")
    .replace("PLACEHOLDER_LABEL", f"tab:{platform}-unique-ads")
    .replace("PLACEHOLDER_ADS", ''.join(ads))
    .replace("PLACEHOLDER_SUGGESTIONS", ''.join(suggestions))

    )

    with open(f"gen/{platform}_unique_apps_table_{spo_to_string(search_page_option)}.tex", 'w') as f:
        f.write(table_template)


def get_unique_items_total(platform, from_search_page, type, cur):
    df = get_all_gids_with_np(android_all if platform == 'android' else ios_all, platform, from_search_page, type, cur)

    sets = {}
    number_games_all = []
    unique_games_per_id = []

    # generate groupings -> we must not join by comment, because not unique anymore when ignoring personalized
    tuples = list(df.groupby(['group_id', 'treatment', 'personalized'])['label'].unique().reset_index().itertuples(name=None, index=False))

    # build all sets
    for group_id, t, p, labels in tuples:
        sets[(group_id, t, p)] = set(labels)

    # build set differences
    for group_id, t, p, labels in tuples:
        target_set = sets[(group_id, t, p)]

        whole_set = reduce(set.union, [sets[k] for k in filter(lambda x: x != (group_id, t, p), sets.keys())])
        # look up comment
        comment = df.loc[(df["group_id"] == group_id) & (df["treatment"] == t) & (df["personalized"] == p)].head(1).iloc[0]["comment"]

        unique_ads = target_set - whole_set

        # get the runs where these ads appear in
        unique_formated = [f"\t\t\t{l} - {list(df.loc[df['label'] == l]['category'].drop_duplicates())[0]}, {list(df.loc[df['label'] == l]['experiment_id'].drop_duplicates())}"
                           for l in unique_ads]
        runs = '\n'.join(unique_formated)
        number_games = len([a for a in unique_formated if "GAME_" in a])
        number_games_all.append(number_games)
        print(group_id, comment, 'Treatment' if t else "Control", 'Personalized' if p else "Unpersonalized", "number games:", number_games)
        print(runs)

        # get ids we have in this run
        ids = list(df.loc[(df['group_id'] == group_id) & (df['treatment'] == t) & (df['personalized'] == p)]['experiment_id'].drop_duplicates())
        for eid in ids:
            unique_games_per_id.append(len([True for u in unique_formated if "GAME_" in u and str(eid) in u]))

    from statistics import mean
    print("average number of unique games per group:", mean(number_games_all))
    print("average number of unique games per id:", mean(unique_games_per_id))




def create_all():
    load_dotenv()
    conn = psycopg.connect(
        dbname=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        host="localhost",
        password=os.environ.get("DB_PASSWORD"),
        port=os.environ.get("DB_PORT"),
    )
    cur = conn.cursor()

    # create jaccard heatmaps for and android (ads vs suggestions) and ios (today vs search)
    print("Creating jaccard heatmaps for baseline (Android).")
    jaccard_sim_heatmap('baseline', [android_baseline_group_id], 'android', None, 'suggestion', 0.341, cur)
    jaccard_sim_heatmap('baseline', [android_baseline_group_id], 'android', None, 'ad', 0.341, cur)

    print("Creating jaccard heatmaps for account parameters (Android).")
    jaccard_sim_heatmap('account_param_persona', android_account_params, 'android', None, 'suggestion', 0.344, cur)
    jaccard_sim_heatmap('account_param_persona', android_account_params, 'android', None, 'ad', 0.344, cur)

    print("Creating jaccard heatmaps for personas (Android).")
    jaccard_sim_heatmap('interest_persona', android_personas, 'android', None, 'suggestion', 0.134, cur)
    jaccard_sim_heatmap('interest_persona', android_personas, 'android', None, 'ad', 0.134, cur)

    print("Creating jaccard heatmaps for baseline (iOS).")
    jaccard_sim_heatmap('baseline', [ios_baseline_id], 'ios', True, 'ad', 0.624, cur)
    jaccard_sim_heatmap('baseline', [ios_baseline_id], 'ios', False, 'ad', 0.624, cur)

    print("Creating jaccard heatmaps for account parameters (iOS).")
    jaccard_sim_heatmap('account_param_persona', ios_account_params, 'ios', True, 'ad', 0.667, cur)
    jaccard_sim_heatmap('account_param_persona', ios_account_params, 'ios', False, 'ad', 0.667, cur)

    print("Creating jaccard heatmaps for personas (iOS).")
    jaccard_sim_heatmap('interest_persona', ios_personas, 'ios', True, 'ad', 0.678, cur)
    jaccard_sim_heatmap('interest_persona', ios_personas, 'ios', False, 'ad', 0.678, cur)

    label_freq_heatmap(android_personas, 'android', None, 'ad', cur)

    # We decided to not include this table in the final paper.
    # gen_unique_app_table(android_all, 'android', None, cur)

    # needs to run 2 times to properly generate legend data (multipass required)
    for run in range(2):
        if run == 1:
            global regenerate
            regenerate = False

        print("Creating stacked bar plots Android...")
        subgraphs = []
        for gid in android_all:
            category_distribution_stacked_bar_plot(gid, 'android', cur)

        print("Creating stacked bar plots iOS...")
        subgraphs = []
        # FIXME not sure if we still need to iterate through persona_types here?
        for persona_type in [[ios_baseline_id], ios_account_params, ios_personas]:
            for gid in persona_type:
                category_distribution_stacked_bar_plot(gid, 'ios', cur)

    # selection for figure 4
    stacked_bar_plot_selection(cur)

    # generate "flamegraphs"
    app_name_flamegraph(android_all, "android", None, 'ad', cur, 10, 5)
    app_name_flamegraph(android_all, "android", None, 'suggestion', cur, 25, 5)
    app_name_flamegraph([ios_baseline_id] + ios_personas + ios_account_params, "ios", False, 'ad', cur, 5, 5)
    app_name_flamegraph([ios_baseline_id] + ios_personas + ios_account_params, "ios", True, 'ad', cur, 10, 5)

    app_name_flamegraph_full(android_all, "android", None, 'ad', cur)
    app_name_flamegraph_full(android_all, "android", None, 'suggestion', cur)
    app_name_flamegraph_full([ios_baseline_id] + ios_personas + ios_account_params, "ios", False, 'ad', cur)
    app_name_flamegraph_full([ios_baseline_id] + ios_personas + ios_account_params, "ios", True, 'ad', cur)

    get_unique_items_total('android', None, 'ad', cur)

if __name__ == "__main__":
    create_all()
