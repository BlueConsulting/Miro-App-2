from rapidfuzz import fuzz
# from sentence_transformers import SentenceTransformer, util
import requests
from pprint import pprint
import pandas as pd

fuzzy_weight = 0.5
# semantic_weight = 0.5
# # Load sentence transformer model (better semantic understanding)
# # model = SentenceTransformer('all-mpnet-base-v2')
# model = SentenceTransformer('paraphrase-MiniLM-L6-v2')

def hybrid_similarity(text1, text2, fuzzy_weight=0.5, semantic_weight=0.5):
    """Combine fuzzy matching & semantic similarity."""
    # Fuzzy similarity (0–100 → 0–1)
    fuzzy_score = fuzz.token_sort_ratio(text1, text2) / 100.0

    # # Semantic similarity (cosine: -1..1 → 0..1)
    # emb1 = model.encode(text1, convert_to_tensor=True)
    # emb2 = model.encode(text2, convert_to_tensor=True)
    # semantic_score = util.cos_sim(emb1, emb2).item()
    # semantic_score = (semantic_score + 1) / 2

    # return (fuzzy_weight * fuzzy_score) + (semantic_weight * semantic_score)
    return (fuzzy_weight * fuzzy_score)



def map_rows(df1, df2, matching, fuzzy_weight=1, semantic_weight=0.5, threshold=0.6):
    import numpy as np
    if matching == 'invoice_migo':
        # Copy input to avoid side effects
        df1 = df1.copy()
        df2 = df2.copy()
        # print(df2)
        # Add new columns
        df1["matching%"] = None
        df1["status"] = "not matched"
        df1["color"] = "r"  # default red
        df2["matching_idx"] = None

        # Columns to copy from df2 → df1
        columns_to_copy = ['grn_description', 'grn_qty', 'grn_rate']
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

            df2.at[j, "matching_idx"] = i

        def unassign(i):
            """Unassign a df1 row."""
            df1.at[i, "status"] = "not matched"
            df1.at[i, "color"] = "r"
            df1.at[i, "matching%"] = None
            for _, new_col in columns_to_copy.items():
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

    else:
        # Copy input to avoid side effects
        df1 = df1.copy()
        df2 = df2.copy()
        # print(df2)
        
        
        # Columns to copy from df2 → df1
        columns_to_copy = ['po_description', 'po_qty', 'po_rate']
        for new_col in columns_to_copy:
            df1[new_col] = None

        # Precompute similarity scores for all pairs
        similarity_matrix = {}
        for i, row1 in df1.iterrows():
            desc1 = str(row1["item_description"]).lower()
            candidates = []
            for j, row2 in df2.iterrows():
                desc2 = str(row2["po_description"]).lower()
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
                val2 = row2['po_rate']

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

            df2.at[j, "matching_idx"] = i

        def unassign(i):
            """Unassign a df1 row."""
            df1.at[i, "status"] = "not matched"
            df1.at[i, "color"] = "r"
            df1.at[i, "matching%"] = None
            for _, new_col in columns_to_copy.items():
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
                desc2 = str(df2.at[j, "po_description"]).lower()
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
    # pprint(df1)
    return df1, df2


