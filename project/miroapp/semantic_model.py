# from sentence_transformers import SentenceTransformer
# import threading

# _model = None
# _lock = threading.Lock()

# def get_model():
#     global _model
#     if _model is None:
#         with _lock:
#             if _model is None:  # double-check
#                 _model = SentenceTransformer("intfloat/e5-small-v2")
#     return _model
