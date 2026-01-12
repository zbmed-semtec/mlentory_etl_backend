# FAIR4ML Schema

This comprehensive guide provides a detailed reference for the FAIR4ML schema properties. For an overview of how FAIR4ML fits into MLentory's schema ecosystem, see [Schemas Overview](schemas.md).

---

## 📋 About This Reference

This document provides detailed explanations of every FAIR4ML property, organized by functional groups. Each property includes:

- **Purpose**: What the property represents
- **Type**: Expected data type
- **Usage**: How it's used in practice
- **Examples**: Real-world examples

**FAIR4ML v0.1.0** (released October 2024) is the current stable version, maintained by the [RDA FAIR4ML Interest Group](https://github.com/RDA-FAIR4ML/FAIR4ML-schema).

### 📚 Official Resources

- **Vocabulary**: [https://w3id.org/fair4ml](https://w3id.org/fair4ml)
- **Specification**: [FAIR4ML v0.1.0](https://rda-fair4ml.github.io/FAIR4ML-schema/release/0.1.0/index.html)
- **Repository**: [RDA-FAIR4ML/FAIR4ML-schema](https://github.com/RDA-FAIR4ML/FAIR4ML-schema)

### 🏷️ Understanding Namespaces

FAIR4ML properties use namespaces to indicate their source:

- **`schema:`** properties come from schema.org (e.g., `schema:name`, `schema:description`)
- **`fair4ml:`** properties are ML-specific (e.g., `fair4ml:mlTask`, `fair4ml:modelCategory`)
- **`codemeta:`** properties come from CodeMeta schema (e.g., `codemeta:readme`)

### 📝 JSON-LD Format

FAIR4ML data is represented in JSON-LD format. The `@context` defines namespaces, and `@type` specifies the entity type:

```json
{
  "@context": {
    "schema": "https://schema.org/",
    "fair4ml": "https://w3id.org/fair4ml#"
  },
  "@type": "fair4ml:MLModel",
  "schema:identifier": ["https://huggingface.co/bert-base-uncased"],
  "schema:name": "BERT Base Uncased",
  "fair4ml:mlTask": ["fill-mask"]
}
```

---

## 🔍 The MLModel Entity: Property Reference

The **MLModel** entity is the heart of FAIR4ML. It represents a trained machine learning model with all its metadata. Let's explore each group of properties in detail, understanding not just what they are, but why they matter and how they're used.

### 🆔 Core Identification

Every model needs a way to be uniquely identified. Think of it like a passport—without proper identification, you can't tell one model from another, and you certainly can't link related information together.

The **`identifier`** property is a list of unique identifiers, typically URLs. It is a list because a model might be available on multiple platforms.For example, a model might have a HuggingFace URL, an arXiv paper URL, and a GitHub repository URL. All of these are valid identifiers, and listing them all helps systems find the model regardless of which platform they're using.

The **`name`** property is the human-readable name of the model. This is what users see when browsing models. It should be descriptive but concise—"BERT Base Uncased" tells you it's a BERT model, the base variant, and it's uncased (doesn't distinguish between uppercase and lowercase).

The **`url`** property is the primary URL where the model can be accessed. This is typically the main platform URL where users can download or use the model. While `identifier` can have multiple values, `url` usually has just one—the canonical location.

Together, these three properties ensure that every model can be uniquely identified, found, and accessed. They're the foundation that makes all other properties meaningful.

### 👤 Authorship and Provenance

Understanding who created a model and who shared it is crucial for attribution, trust, and legal compliance. FAIR4ML distinguishes between two related but different concepts:

**`author`** represents the person or organization who actually created the model. This is the intellectual creator: the researcher or team who designed and trained the model. For example, Google created BERT, so "Google" would be the author.

**`sharedBy`** represents the person or organization who shared the model online. This might be the same as the author, but often it's different. For example, a researcher might create a model, but HuggingFace might host and share it. In that case, the author is the researcher, and HuggingFace is who shared it.

This distinction matters because:

- **Attribution**: You want to credit the right person
- **Licensing**: The author and the platform might have different licensing terms
- **Support**: Questions about the model might go to the author, while platform issues go to the sharer
- **Trust**: Understanding the source helps users evaluate model quality

### 📅 Temporal Information

Dates in FAIR4ML help you understand the model's lifecycle and relevance. Three dates are particularly important:

**`dateCreated`** is when the model was first created. This might be when training started, when the model architecture was finalized, or when the first version was saved. This date helps you understand how old the model is and whether newer versions might exist.

**`dateModified`** is when the model was last changed. This could be a retraining, a bug fix, or an update to the model weights. If you're using a model, you want to know if it's been updated since you last checked.

**`datePublished`** is when the model was made publicly available. This is different from creation—a model might be created in 2020 but not published until 2021. This date is important for understanding when the model became available to the community.

These dates help researchers understand model evolution, track updates, and make decisions about which version to use.

### 📝 Description and Documentation

The description properties help users understand what the model does and how to use it:

**`description`** is a full textual description of the model. This is typically extracted from model cards or README files. It explains what the model does, how it was trained, and what it's good for. A good description helps users quickly determine if a model is relevant to their needs.

**`keywords`** are tags or labels that describe the model. These are typically short, searchable terms like "bert", "transformer", "nlp", "masked-language-modeling". Keywords help with discovery—when someone searches for "transformer models," models with "transformer" in their keywords will appear.

**`inLanguage`** specifies which natural languages the model works with. This is represented using ISO 639-1 language codes (e.g., "en" for English, "de" for German, "fr" for French). A multilingual model might have multiple language codes. This property is crucial for users who need models for specific languages.

**`license`** specifies the legal terms under which the model is distributed. Common licenses include "apache-2.0", "mit", "cc-by-4.0", and others. Understanding the license is essential for commercial use, redistribution, and compliance.

**`referencePublication`** links to research papers that describe the model. This is typically an arXiv URL, DOI, or other publication identifier. These papers provide the theoretical foundation, training details, and evaluation results that help users understand the model deeply.

### 🤖 ML Task and Category

These are the most ML-specific properties in FAIR4ML, and they're crucial for model discovery:

**`mlTask`** specifies what machine learning task(s) the model addresses. This is an array because models can often perform multiple tasks. Common tasks include:

- `fill-mask`: Predicting masked words in text (like BERT)
- `text-generation`: Generating new text
- `text-classification`: Classifying text into categories
- `image-classification`: Classifying images
- `object-detection`: Finding objects in images
- `question-answering`: Answering questions based on context
- `summarization`: Creating summaries
- `translation`: Translating between languages

When someone searches for "models for sentiment analysis," systems can match this to models with `mlTask` containing "text-classification" or "sentiment-analysis".

**`modelCategory`** describes the model's architecture or category. This helps users understand the technical approach:

- `transformer`: Transformer-based models (BERT, GPT, etc.)
- `CNN`: Convolutional Neural Networks
- `RNN`: Recurrent Neural Networks
- `LLM`: Large Language Models
- `BERT`, `GPT`, `ResNet`, `VGG`: Specific architecture families

This property helps researchers find models with specific architectures, which is important for understanding performance characteristics, computational requirements, and use cases.

### 🌳 Model Lineage

Model lineage tracks how models are related to each other, which is crucial for understanding model evolution and dependencies:

**`fineTunedFrom`** specifies the base model(s) that this model was fine-tuned from. Fine-tuning is the process of taking a pre-trained model and adapting it for a specific task. For example, a sentiment analysis model might be fine-tuned from BERT. This property creates a family tree of models, showing how they're related.

This is an array because:

- A model might be fine-tuned from multiple base models (ensemble approaches)
- Multi-stage fine-tuning might involve intermediate models
- Some models combine features from multiple base models

Understanding lineage helps users:

- Find related models that might be better suited to their needs
- Understand model capabilities (a model fine-tuned from BERT inherits BERT's capabilities)
- Track model evolution and improvements
- Identify base models that might be more general-purpose

### 💻 Usage and Code

These properties help users actually use the model:

**`intendedUse`** describes what the model is designed for. This might be "Research", "Commercial applications", "Educational purposes", or more specific use cases. This helps users determine if the model is appropriate for their needs and understand any restrictions.

**`usageInstructions`** provides step-by-step instructions on how to use the model. This might include installation commands, loading code, input formats, and output interpretations. Good usage instructions save users hours of trial and error.

**`codeSampleSnippet`** is actual code that demonstrates model usage. This is typically a short Python snippet showing how to load and use the model. Code examples are invaluable because they show exactly what works, reducing the barrier to entry for new users.

### ⚠️ Ethics and Risks

These properties address the critical responsibility of documenting model limitations and ethical considerations:

**`modelRisksBiasLimitations`** describes known issues with the model. This might include:

- Performance limitations (e.g., "Works poorly on non-standard English")
- Bias issues (e.g., "May exhibit gender bias in certain contexts")
- Data limitations (e.g., "Trained only on English text")
- Use case restrictions (e.g., "Not suitable for medical diagnosis")

This information is crucial for responsible AI deployment. Users need to understand limitations to avoid misuse and to make informed decisions about when the model is appropriate.

**`ethicalSocial`** addresses broader ethical and social considerations. This might include:

- Potential misuse cases (e.g., "Should not be used for surveillance")
- Social impact considerations
- Fairness and equity concerns
- Community guidelines

**`legal`** covers legal considerations, including:

- Liability disclaimers
- Compliance requirements
- Jurisdictional restrictions
- Data protection considerations

These properties help ensure models are used responsibly and ethically, which is increasingly important as AI systems become more powerful and widespread.

### 📊 Training and Evaluation Data

Understanding what data a model was trained and evaluated on is crucial for:

- Reproducing results
- Understanding model capabilities and limitations
- Assessing model quality
- Making informed decisions about model suitability

**`trainedOn`** lists the datasets used for training. This is an array because models are often trained on multiple datasets. For example, BERT was trained on Wikipedia and BookCorpus. Knowing training data helps users understand:

- What the model has seen during training
- Potential biases (if training data is biased, the model likely is too)
- Domain coverage (what types of data the model understands)
- Data quality implications

**`testedOn`**, **`validatedOn`**, and **`evaluatedOn`** specify datasets used for different stages of model development:

- **Tested on**: Datasets used for final testing before release
- **Validated on**: Datasets used for validation during development
- **Evaluated on**: Datasets used for benchmarking and comparison

These distinctions help researchers understand the rigor of model evaluation and the contexts in which performance was measured.

**`evaluationMetrics`** lists the metrics and their values. This might include "F1: 0.92", "Accuracy: 0.89", "BLEU: 0.85", or other task-specific metrics. These metrics help users:

- Compare models on the same benchmarks
- Understand model performance quantitatively
- Make informed decisions about which model to use
- Set expectations for model performance

### 🔗 Additional URLs

These properties provide links to additional resources:

**`discussionUrl`** links to forums, GitHub discussions, or other places where users can ask questions and share experiences. This is valuable for getting help and learning from the community.

**`archivedAt`** links to archive services (like Internet Archive) where the model is preserved. This ensures long-term accessibility even if the primary platform disappears.

**`readme`** links to the README file, which typically contains comprehensive documentation, examples, and troubleshooting information.

**`issueTracker`** links to bug trackers or issue management systems where users can report problems and track fixes.

### ⚙️ Technical and Environmental Information

**`memoryRequirements`** specifies the computational resources needed to run the model. This might be "512MB RAM, 2GB disk space" or more detailed specifications. This helps users determine if they have the resources to use the model.

**`hasCO2eEmissions`** documents the carbon footprint of training the model. This is increasingly important as the environmental impact of large-scale ML training becomes a concern. Values might be "15.2 kg CO2e" or similar. This helps researchers make environmentally conscious choices.

### 🔧 Platform-Specific Extensions

**`metrics`** is a MLentory-specific extension that stores platform-specific metrics like download counts, likes, stars, or other engagement metrics. While not part of the official FAIR4ML specification, this provides valuable context about model popularity and community adoption.

**`extraction_metadata`** is another MLentory extension that tracks how each field was extracted. This includes:

- **`extraction_method`**: How the field was obtained (e.g., "Parsed_from_HF_dataset", "Inferred_from_tags")
- **`confidence`**: How confident we are in the extraction (0.0 to 1.0)
- **`source_field`**: The original field name in the source data
- **`notes`**: Additional context about the extraction

This metadata is crucial for:

- Debugging transformation issues
- Understanding data quality
- Tracking provenance
- Improving extraction methods

---

## 🔗 Related Entities: The Ecosystem

ML models don't exist in isolation—they're part of a rich ecosystem of datasets, papers, authors, and organizations. FAIR4ML references other schemas to describe these related entities:

**Datasets** use the **Croissant ML** schema, which extends schema.org's Dataset with ML-specific properties. This ensures that training and evaluation datasets are described consistently, enabling users to understand the full context of model development.

**Papers** use **Schema.org ScholarlyArticle**, which provides properties for research publications. This links models to their theoretical foundations and evaluation results.

**Authors** and **Organizations** use standard Schema.org types, ensuring compatibility with other systems that track researchers and institutions.

**Tasks** use **Schema.org DefinedTerm** to represent ML tasks in a structured way, enabling better categorization and discovery.

**Licenses** use **Schema.org CreativeWork** to represent license information, ensuring legal clarity.

This ecosystem approach means that models, datasets, papers, and people can all be described using compatible schemas, creating a rich, interconnected knowledge graph of ML research and development.

---

## 💡 Complete Example: Seeing It All Together

Let's look at a complete FAIR4ML model description to see how all these properties work together:

```json
{
  "@context": {
    "schema": "https://schema.org/",
    "fair4ml": "https://w3id.org/fair4ml#"
  },
  "@type": "fair4ml:MLModel",
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "BERT Base Uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "Google",
  "sharedBy": "huggingface",
  "dateCreated": "2018-10-11T00:00:00Z",
  "datePublished": "2018-10-11T00:00:00Z",
  "description": "BERT model for masked language modeling, pre-trained on English Wikipedia and BookCorpus",
  "keywords": ["bert", "transformer", "nlp", "masked-language-modeling"],
  "inLanguage": ["en"],
  "license": "apache-2.0",
  "referencePublication": ["https://arxiv.org/abs/1810.04805"],
  "mlTask": ["fill-mask"],
  "modelCategory": ["transformer", "bert"],
  "fineTunedFrom": [],
  "intendedUse": "Research and commercial applications",
  "usageInstructions": "Load with transformers library: AutoModel.from_pretrained('bert-base-uncased')",
  "codeSampleSnippet": "from transformers import AutoModel; model = AutoModel.from_pretrained('bert-base-uncased')",
  "modelRisksBiasLimitations": "Model may exhibit bias against certain demographics",
  "trainedOn": [
    "https://huggingface.co/datasets/wikipedia",
    "https://huggingface.co/datasets/bookcorpus"
  ],
  "evaluatedOn": [
    "https://huggingface.co/datasets/glue"
  ],
  "evaluationMetrics": [
    "GLUE Score: 80.5",
    "F1: 0.92"
  ],
  "readme": "https://huggingface.co/bert-base-uncased/blob/main/README.md",
  "memoryRequirements": "512MB RAM",
  "metrics": {
    "downloads": 5000000,
    "likes": 2500
  }
}
```

This example shows a complete, realistic model description. Notice how:

- Core identification ensures the model can be found
- Authorship provides attribution
- Temporal information shows when it was created
- Description and keywords help with discovery
- ML-specific properties (mlTask, modelCategory) enable task-based search
- Training and evaluation data provide context
- Ethics and risks ensure responsible use
- Additional URLs provide resources for users

---

## 🔄 FAIR4ML Versions and Evolution

FAIR4ML v0.1.0, released in October 2024, represents the first stable version with comprehensive ML model properties. The development process involved extensive community feedback through the RDA FAIR4ML Interest Group, ensuring the vocabulary meets real-world needs.

Future versions are being actively discussed and will likely include:

- **Structured evaluation metrics**: Instead of free-form strings, structured representations of metrics and their values
- **Hyperparameter representation**: Standardized ways to describe model hyperparameters
- **Model generation process**: Detailed information about how the model was created
- **External validation**: Information about third-party evaluations and certifications

This evolutionary approach ensures FAIR4ML stays relevant as the ML field evolves while maintaining backward compatibility.

---

## 🌐 Compatibility: Working with Other Standards

FAIR4ML is designed to work seamlessly with other research metadata schemas. This compatibility is crucial because ML models are part of a larger research ecosystem:

**Schema.org Extensions** like Bioschemas (for life sciences), CodeMeta (for research software), and Croissant ML (for ML datasets) all use the same foundation, enabling rich, interconnected descriptions.

**RDA Standards** like Research Metadata Schemas and FAIR Digital Objects provide frameworks for packaging and describing research artifacts, and FAIR4ML models fit naturally into these frameworks.

This compatibility means:

- Models can be described alongside their datasets using compatible schemas
- Models can reference their software dependencies using CodeMeta
- Models can be packaged as FAIR Digital Objects for preservation and sharing
- Cross-platform discovery becomes possible because different systems can understand the same metadata

---

## 🎓 Key Takeaways

FAIR4ML is more than just a vocabulary—it's a foundation for making ML models findable, accessible, interoperable, and reusable. By standardizing how models are described, FAIR4ML enables:

- **Unified search** across different platforms
- **Automated processing** of model metadata
- **Rich relationships** between models, datasets, papers, and people
- **Responsible AI** through comprehensive documentation of limitations and ethics
- **Research reproducibility** through detailed training and evaluation information

Whether you're a researcher looking for the right model, a developer building ML tools, or someone interested in making AI more accessible, understanding FAIR4ML helps you work more effectively with ML model metadata.

---

## 📖 Further Reading

To dive deeper into FAIR4ML:

- **FAIR4ML Repository:** [https://github.com/RDA-FAIR4ML/FAIR4ML-schema](https://github.com/RDA-FAIR4ML/FAIR4ML-schema) - Source code, issues, and discussions
- **FAIR4ML Vocabulary:** [https://w3id.org/fair4ml](https://w3id.org/fair4ml) - Interactive vocabulary browser
- **Research Paper:** [FAIR4ML, a vocabulary to describe Machine/Deep Learning models](https://zenodo.org/records/16735334) - Academic paper explaining the design
- **Schema.org:** [https://schema.org/](https://schema.org/) - Foundation vocabulary
- **RDA FAIR4ML Interest Group:** [RDA FAIR4ML-IG](https://www.rd-alliance.org/groups/fair-machine-learning-ig) - Community and discussions

---

## 🚀 Next Steps

Explore how FAIR4ML is used in MLentory:

- **[Schemas Overview](schemas.md)** → How FAIR4ML fits with Croissant and Schema.org
- **[Schema Structure](structure.md)** → Pydantic implementation details
- **[Source Schemas](source-schemas.md)** → How source data maps to FAIR4ML
- **[Transformers Overview](../transformers/overview.md)** → Transformation process
