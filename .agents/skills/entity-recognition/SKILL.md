---
name: entity-recognition
description: Use when extracting structured named entities, classifications, or domain taxonomy terms from text or documents into JSON format
---

# Entity Recognition & Taxonomy Extraction

## Overview
Standardized directives for high-precision named entity recognition (NER), domain classification, and semantic indexing from multimodal document text. Designed specifically for Pixeltable auto-split schema generation.

## When to Use
- Extracting people, organizations, locations, dates, and products from unstructured text.
- Enriching raw files with structured semantic search columns.
- Standardizing entity naming across multi-document repositories.

## Prompt Directives & Operational Rules
When `/entity-recognition` is invoked in a prompt, the model must follow these operational rules:

1. **Extraction Taxonomy**:
   - `entities_people`: List of full names of identified individuals.
   - `entities_organizations`: List of companies, institutions, agencies, and groups.
   - `entities_locations`: List of physical places, cities, countries, and geopolitical entities.
   - `entities_dates`: List of normalized dates or temporal references (YYYY-MM-DD or year strings where possible).
   - `classification_domain`: Single concise primary domain or topic category (e.g. "Biomedicine", "Legal", "Technology", "Art History").
   - `key_concepts`: List of 3 to 7 high-salience thematic keywords.
   - `entity_summary`: A 1-2 sentence factual synopsis linking the primary identified entities.
   - `extraction_confidence`: Estimated confidence float between 0.0 and 1.0.

2. **Output Format**:
   - When JSON mode or auto-split is requested, output MUST be a valid JSON object matching the schema above.
   - Do NOT invent or extrapolate entities not grounded in the source text.
   - If a category contains no entities, return an empty array `[]`.

3. **Example Output**:
```json
{
  "entities_people": ["Ada Lovelace", "Charles Babbage"],
  "entities_organizations": ["Royal Society", "Analytical Engine Laboratory"],
  "entities_locations": ["London", "United Kingdom"],
  "entities_dates": ["1843", "1871"],
  "classification_domain": "Computer Science History",
  "key_concepts": ["mechanical computation", "algorithm design", "early computing"],
  "entity_summary": "Ada Lovelace collaborated with Charles Babbage on algorithms for the Analytical Engine.",
  "extraction_confidence": 0.98
}
```
