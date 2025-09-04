#!/usr/bin/env python3

"""Helper functions for generate_plots.py"""

import os.path
import pandas as pd

def spo_to_string(spo):
    if spo:
        return "search"
    elif spo is False:
        return "today"
    elif spo is None:
        return "both"

def fetch_run(idx_c, idx_t, platform, from_search_page, type, cur):
    ## create cache if missing
    if not os.path.exists('plot_cache'):
        os.makedirs('plot_cache')

    ## check cache for this entry
    path = f"plot_cache/{idx_c}_{idx_t}_{spo_to_string(from_search_page)}_{type}.csv"
    if os.path.isfile(path):
        return pd.read_csv(path)
    else:
        ## create the cache file if it does not exist
        if platform == "ios":
            if from_search_page is None:
                search_page = ""
            elif from_search_page is True:
                search_page = "AND from_search_page"
            elif from_search_page is False:
                search_page = "AND NOT from_search_page"
            else:
                raise RuntimeError("Invalid state.")

            query = f"""
            SELECT ad_data.id, ad_data.experiment_id, ad_data.time,
                ad_data.label, app_detail.data->'relationships'->'genres'->'data'->0->'attributes'->>'name' as category,
                ad_data.sub_label,
                ad_data.app_id, ad_data.from_search_page, ad_data.type,
                experiment.device_serial, experiment.group_id, experiment.sub_group_id, experiment.comment,
                experiment.treatment, experiment.personalized
            FROM ad_data
            JOIN app_detail ON app_detail.id = ad_data.app_id
            JOIN experiment ON experiment.id = ad_data.experiment_id
            WHERE experiment_id in ({idx_c}, {idx_t})
            AND type = '{type}'
            {search_page};
            """
        elif platform == 'android':
            query = f"""
            SELECT ad_data.id, ad_data.experiment_id, ad_data.time,
                ad_data.label, app_detail.data->>'applicationCategory' AS category,
                ad_data.sub_label,
                ad_data.app_id, ad_data.from_search_page, ad_data.type,
                experiment.device_serial, experiment.group_id, experiment.sub_group_id, experiment.comment,
                experiment.treatment, experiment.personalized
            FROM ad_data
            JOIN app_detail ON app_detail.id = ad_data.app_id
            JOIN experiment ON experiment.id = ad_data.experiment_id
            WHERE experiment_id in ({idx_c}, {idx_t})
            AND type = '{type}';
            """
        else:
            raise RuntimeError(f"Invalid platform '{platform}'.")

        cur.execute(query)
        data = cur.fetchall()
        df = pd.DataFrame(data, columns=['id', 'experiment_id', 'time', 'label', 'category', 'sub_label', 'app_id', 'from_search_page', 'type', 'device_serial', 'group_id', 'sub_group_id', 'comment', 'treatment', 'personalized'])
        df = df.sort_values(by="time")

        # check and normalize length
        len_c = len(df.loc[df["experiment_id"] == idx_c])
        len_t = len(df.loc[df["experiment_id"] == idx_t])

        # remove NoneType values
        df = df.loc[~df["category"].isnull()]

        m = min(len_c, len_t)
        print(f"Original length ({idx_c} / {idx_t}):", len_c, len_t)
        print(f"Normalizing to {m}")

        if len_c > m:
            number_to_cut = len_c - m
            row_idx_to_remove = df.loc[df["experiment_id"] == idx_c].tail(number_to_cut).index
            df = df[~df.index.isin(row_idx_to_remove)]

        if len_t > m:
            number_to_cut = len_t - m
            row_idx_to_remove = df.loc[df["experiment_id"] == idx_t].tail(number_to_cut).index
            df = df[~df.index.isin(row_idx_to_remove)]

        # save cache file
        df.to_csv(path)

        return df


def get_all(group_id, platform, from_search_page, type, cur):
    return pd.concat([fetch_run(idx_c, idx_t, platform, from_search_page, type, cur)
                      for idx_c, idx_t in fetch_ids(group_id, cur)])

def get_all_with_np(group_id, platform, from_search_page, type, cur):
    return pd.concat([pd.concat([fetch_run(idx_c, idx_t, platform, from_search_page, type, cur),
                                 fetch_run(idx_cnp, idx_tnp, platform, from_search_page, type, cur)])
                      for idx_c, idx_t, idx_cnp, idx_tnp in fetch_ids_with_np(group_id, cur)])

def get_all_gids(group_ids, platform, from_search_page, type, cur):
    """Takes a list of group ids and returns all the matching dataframes."""
    return pd.concat([get_all(gid, platform, from_search_page, type, cur)
                      for gid in group_ids])

def get_all_gids_with_np(group_ids, platform, from_search_page, type, cur):
    """Takes a list of group ids and returns all the matching dataframes."""
    return pd.concat([get_all_with_np(gid, platform, from_search_page, type, cur)
                      for gid in group_ids])

def fetch_ids(group_id, cur, expected_len = 5):
    """Fetches the indiviual experiment ids (only personalized) for a group_id.
    Returns: (control_id, treatment_id) tuples."""
    # fetch all ids for a experiment group
    cur.execute(f"""
    select a.id,b.id from experiment a
    join experiment b on a.sub_group_id = b.sub_group_id
    where a.group_id = '{group_id}'
    and not a.treatment
    and b.treatment
    and a.personalized
    and b.personalized
    order by a.sub_group_id;
    """)

    res = cur.fetchall()
    if (len(res) != expected_len):
        print(f"Unexpected length: {len(res)} - in {group_id} (function fetch_ids)")
    return res

def fetch_ids_with_np(group_id, cur, expected_len = 5):
    """Fetches the indiviual experiment ids including unpersonalized entries for a group_id.
    Returns: (control_id, treatment_id, control_id_np, treatment_id_np) tuples."""

    # fetch all ids for a experiment group
    cur.execute(f"""
    SELECT a.id AS id_control, b.id AS id_treatment, c.id AS id_control_np, d.id AS id_treatment_np
    FROM experiment a
    JOIN experiment b ON a.sub_group_id = b.sub_group_id
    JOIN experiment c ON c.sub_group_id = a.sub_group_id
    JOIN experiment d ON d.sub_group_id = a.sub_group_id
    WHERE a.group_id = '{group_id}'
    AND b.group_id = '{group_id}'
    AND c.group_id = '{group_id}'
    AND d.group_id = '{group_id}'
    AND a.id != b.id AND c.id != d.id
    AND NOT a.treatment AND a.personalized
    AND b.treatment AND b.personalized
    AND NOT c.treatment AND NOT c.personalized
    AND d.treatment AND NOT d.personalized
    """)

    res = cur.fetchall()
    if (len(res) != expected_len):
        print(f"Unexpected length: {len(res)} - in {group_id} (function fetch_ids_with_np)")
    return res
