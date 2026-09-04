# Feature: Multimodal Vision & Entity Classification Engines

- **Feature ID**: `multimodal-vision`
- **Status**: Requirements & Planned Architecture (Phase 4)
- **Primary Goal**: Expand beyond LLMs to specialized vision classifiers and zero-shot entity extraction models.

---

## 1. Overview & Vision

While Ollama and Gemini handle generative reasoning, specialized machine learning models provide **100x faster and cheaper execution** for dedicated perception tasks like image style classification, object recognition, and entity extraction. 

This feature introduces native support for:
1. **Ultralytics YOLO Vision Classifiers**: e.g., WikiArt 27-movement painting classifier (`keremberke/yolov8m-painting-classification`).
2. **GLiNER Zero-Shot Named Entity Recognition**: Fast token classification without generative prompt latency or hallucinations.
3. **Hugging Face Hub Pipelines**: Direct integration with local transformer models via Pixeltable `@pxt.udf`.

---

## 2. Core Requirements

### 2.1 27-Class Art Taxonomy Classifier
- Classify artwork images across 27 canonical movements:
  `['Abstract_Expressionism', 'Action_painting', 'Analytical_Cubism', 'Art_Nouveau_Modern', 'Baroque', 'Color_Field_Painting', 'Contemporary_Realism', 'Cubism', 'Early_Renaissance', 'Expressionism', 'Fauvism', 'High_Renaissance', 'Impressionism', 'Mannerism_Late_Renaissance', 'Minimalism', 'Naive_Art_Primitivism', 'New_Realism', 'Northern_Renaissance', 'Pointillism', 'Pop_Art', 'Post_Impressionism', 'Realism', 'Rococo', 'Romanticism', 'Symbolism', 'Synthetic_Cubism', 'Ukiyo_e']`
- Output structured predictions (`predicted_class`, `confidence`, `probabilities_json`).

### 2.2 GLiNER Zero-Shot NER (`urchade/gliner`)
- Extract arbitrary entity types (`person`, `location`, `organization`, `date`, `artwork`, `technique`) on CPU or GPU.
- Directly feed extracted entities into the active table schema and `{domain}_{table}_context.md` register.

### 2.3 Declarative Pixeltable UDF Architecture
- Wrap vision and NER models into `@pxt.udf` functions.
- Run as computed columns on Pixeltable tables with automatic result caching in PostgreSQL.
- Support Auto-Split unpack so JSON fields become separate indexed columns.

---

## 3. Implementation Plan & Checklist

- [ ] **Phase 1: Ultralytics & Hugging Face Integration Core**
  - [ ] Implement wrapper module `src/core/vision_models.py`.
  - [ ] Add optional dependency extras in `pyproject.toml` (`[project.optional-dependencies] vision = ["ultralytics", "transformers"]`).
  - [ ] Register `@pxt.udf` for image classification.
- [ ] **Phase 2: GLiNER Entity Extraction Engine**
  - [ ] Implement `src/core/gliner_ner.py` supporting custom zero-shot labels.
  - [ ] Auto-split extracted entity spans into canonical entity columns.
- [ ] **Phase 3: UI Controls & Playground Integration**
  - [ ] Add "Model Category" selector in Data Enhancement (LLM Generative vs Vision Classifier vs Zero-Shot NER).
  - [ ] Support sample row testing and batch column creation.
