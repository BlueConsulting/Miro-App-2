from pprint import pprint
import pandas as pd

from rapidfuzz import fuzz
from numpy import dot
from numpy.linalg import norm
# from .semantic_model import get_model
import re
import requests




def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def semantic_similarity(a, b):
    url = rf"http://20.40.43.125:8020/similarity"
    resp = requests.post(
        url,
        json={"text1": a, "text2": b},
        timeout=5
    )
    return resp.json()["similarity"]

def fuzzy_similarity(a: str, b: str) -> float:
    return (
        0.5 * fuzz.token_set_ratio(a, b) +
        0.3 * fuzz.partial_ratio(a, b) +
        0.2 * fuzz.ratio(a, b)
    ) / 100.0


def hybrid_similarity(
    text1: str,
    text2: str,
    fuzzy_weight: float,
    semantic_weight: float,
):
    a = normalize(text1)
    b = normalize(text2)

    if not a or not b:
        return 0.0

    try:
        fuzzy_score = fuzzy_similarity(a, b)
        semantic_score = semantic_similarity(a, b)

        return (
            fuzzy_weight * fuzzy_score +
            semantic_weight * semantic_score
        )

    except Exception:
        # fallback: fuzzy only
        return fuzzy_similarity(a, b)
    


def map_rows(df1, df2, matching, fuzzy_weight=0.5, semantic_weight=0.5, threshold=0.6):
    import numpy as np
    # Copy input to avoid side effects
    df1 = df1.copy()
    df2 = df2.copy()
    # print(df2)
    # Add new columns
    df1["matching%"] = None
    df1["status"] = "not matched"
    df1["color"] = "r"  # default red
    df1["index_matching"] = None
    df2["matching_idx"] = None
    columns_to_copy = ['grn_description', 'grn_qty', 'grn_rate']
    # Columns to copy from df2 → df1
    if matching == "3way":
        columns_to_copy = ['grn_description', 'grn_qty', 'grn_rate', 'po_qty', 'po_rate']
    for new_col in columns_to_copy:
        df1[new_col] = None

    # Precompute similarity scores for all pairs
    similarity_matrix = {}
    for i, row1 in df1.iterrows():
        desc1 = str(row1["item_description"]).lower()
        candidates = []
        for j, row2 in df2.iterrows():
            desc2 = str(row2["grn_description"]).lower()
            score = hybrid_similarity(desc1, desc2, fuzzy_weight, semantic_weight)
            # print(score)
            candidates.append((j, score))
        # Sort descending by similarity
        candidates.sort(key=lambda x: x[1], reverse=True)
        similarity_matrix[i] = candidates

    def try_assign(i, candidates):
        """Try to assign df1[i] to best available df2 using conflict resolution + numeric check."""
        row1 = df1.loc[i]

        for j, score in candidates:
            if score < threshold:
                break  # too weak

            row2 = df2.loc[j]

            # --- numeric comparison (second parameter check) ---
            numeric_match = True
            
            val1 = row1['unit_price']
            val2 = row2['grn_rate']

            if pd.notna(val1) and pd.notna(val2):
                if abs(float(val1) - float(val2)) > 1:
                    numeric_match = False
                    break

            if not numeric_match:
                continue  # skip this candidate, try next

            # --- conflict resolution logic ---
            if pd.isna(df2.at[j, "matching_idx"]):  
                # free → assign
                assign(i, j, score)
                return True
            else:
                # already matched → check conflict
                prev_i = df2.at[j, "matching_idx"]
                prev_score = df1.at[prev_i, "matching%"]

                if score > prev_score:  # current match is stronger
                    unassign(prev_i)
                    assign(i, j, score)
                    # retry previous df1 row with its next-best match
                    try_assign(prev_i, similarity_matrix[prev_i][1:])
                    return True
                else:
                    continue  # skip to next candidate

        return False  # no valid match found


    def assign(i, j, score):
        """Assign df1[i] to df2[j]."""
        # Copy data from df2 → df1
        for new_col in columns_to_copy:
            if new_col in df2.columns:
                df1.at[i, new_col] = df2.at[j, new_col]

        df1.at[i, "matching%"] = round(score * 100, 2)
        df1.at[i, "status"] = "matched"
        df1.at[i, "color"] = "g"
        df1.at[i, "index_matching"] = j  # ✅ df2 index

        df2.at[j, "matching_idx"] = i

    def unassign(i):
        """Unassign a df1 row."""
        df1.at[i, "status"] = "not matched"
        df1.at[i, "color"] = "r"
        df1.at[i, "matching%"] = None
        df1.at[i, "index_matching"] = None
        for _, new_col in columns_to_copy:
            df1.at[i, new_col] = None

    # Main loop: try to assign each df1 row
    for i in df1.index:
        try_assign(i, similarity_matrix[i])

    # Fallback pass: description-only matching for unmatched
    unmatched_df1 = df1[df1["status"] == "not matched"]
    unmatched_df2 = df2[df2["matching_idx"].isna()]

    for i in unmatched_df1.index:
        desc1 = str(df1.at[i, "item_description"]).lower()
        best_j, best_score = None, -1
        for j in unmatched_df2.index:
            desc2 = str(df2.at[j, "grn_description"]).lower()
            score = hybrid_similarity(desc1, desc2, fuzzy_weight, semantic_weight)
            if score > best_score:
                best_j, best_score = j, score

        if best_j is not None:
            if best_score >= threshold:
                assign(i, best_j, best_score)
                df1.at[i, "status"] = "probable"
                df1.at[i, "color"] = "y"
            else:
                df1.at[i, "matching%"] = round(best_score * 100, 2)
                df1.at[i, "status"] = "unmatched"
                df1.at[i, "color"] = "r"

    # ---- append unmatched df2 rows into df1 ----
    unmatched_df2 = df2[df2["matching_idx"].isna()]

    new_rows = []
    for j, row in unmatched_df2.iterrows():
        new_row = {col: '-' for col in df1.columns}

        for new_col in columns_to_copy:
            if new_col in df2.columns and new_col in df1.columns:
                new_row[new_col] = row[new_col]

        new_row["index_matching"] = j   # ✅ df2 index
        new_row["status"] = "unmatched_df2"
        new_row["color"] = "r"
        new_row["matching%"] = None

        new_rows.append(new_row)

    if new_rows:
        df1 = pd.concat([df1, pd.DataFrame(new_rows)], ignore_index=True)

    df1 = df1.where(pd.notna(df1), None)
    pprint(df1)
    return df1, df2

def validate_row(row):
    # Skip validation if not matched
    if row["status"] != "matched":
        return row["status"], "No record passed matching threshold from MIGO for this record"

    status = "matched"
    reasons = []   # 👈 collect all reasons here

    po_qty = float(row["po_qty"])
    grn_qty = float(row["grn_qty"])
    inv_qty = float(row["item_quantity"])
    po_rate = float(row["po_rate"])
    inv_rate = float(row["unit_price"])

    # Rule 1: PO qty >= GRN qty
    if po_qty < grn_qty:
        status = "not_matched"
        reasons.append("PO quantity cannot be less than GRN quantity for item")

    # Rule 2: GRN qty == Invoice qty
    if grn_qty != inv_qty:
        status = "not_matched"
        reasons.append("GRN quantity does not match with Invoice quantity for item")

    # Rule 3: PO rate == Invoice unit price
    if po_rate != inv_rate:
        status = "not_matched"
        reasons.append("PO rate does not match with Invoice rate for item")

    # Join reasons using newline so frontend shows each on new line
    reason_text = "\n".join(reasons)

    return status, reason_text


def validate_row_2way(row):
    # Skip validation if not matched
    if row["status"] != "matched":
        return row["status"], "No record passed matching threshold from MIGO for this record"

    

    # Rule 2: GRN qty == Invoice qty
    if float(row["grn_qty"]) != float(row["item_quantity"]):
        return "not_matched", "GRN quantity does not match with Invoice quantity for item"

    

    # All rules passed
    return "matched", ""

if __name__ == "__main__":
    print(hybrid_similarity('charger','adapter'))


