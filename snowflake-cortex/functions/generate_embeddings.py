import os
import sys

# Cache the model across invocations
_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        # noinspection PyTypeChecker
        import_dir: str = sys._xoptions.get('snowflake_import_directory')
        model_path = os.path.join(import_dir, 'minilm/')
        _model = SentenceTransformer(model_path)
    return _model


def generate_embeddings(input_text: str) -> list:
    model = get_model()
    embedding = model.encode(input_text)
    return embedding.tolist()
