"""
Build LLM prompts for HF model card schema property extraction.

Loads property definitions and templates from ``config/hf_schema_extraction/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant designed to extract specific information "
    "based on provided criteria. Think carefully what the extraction task is, "
    "and then strictly answer as instructed."
)

QUESTIONS_FILENAME = "llm_questions.csv"
TEMPLATES_FILENAME = "llm_templates.csv"


@dataclass(frozen=True)
class PropertyPrompt:
    """A single property extraction prompt for one model card."""

    property_name: str
    template_type: str
    question: str
    instruction: str
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    def to_chat_messages(self) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.instruction},
        ]


class LLMSchemaPromptBuilder:
    """Load schema extraction metadata and build per-property prompts."""

    def __init__(self) -> None:
        self.questions: Dict[str, str] = {}
        self.prop_template_type_map: Dict[str, str] = {}
        self.templates: Dict[str, str] = {}

    @property
    def property_names(self) -> List[str]:
        return list(self.questions.keys())

    def load_metadata(self, metadata_dir: str | Path) -> None:
        """
        Load ``llm_questions.csv`` and ``llm_templates.csv`` from *metadata_dir*.

        Raises:
            FileNotFoundError: If required CSV files are missing.
        """
        base = Path(metadata_dir)
        questions_file = base / QUESTIONS_FILENAME
        templates_file = base / TEMPLATES_FILENAME

        if not questions_file.is_file():
            raise FileNotFoundError(f"LLM questions file not found: {questions_file}")
        if not templates_file.is_file():
            raise FileNotFoundError(f"LLM templates file not found: {templates_file}")

        questions_df = pd.read_csv(questions_file, sep=";")
        self.questions = questions_df.set_index("Property")["Question"].to_dict()
        self.prop_template_type_map = questions_df.set_index("Property")[
            "Template_Type"
        ].to_dict()

        templates_df = pd.read_csv(templates_file, sep=";")
        self.templates = templates_df.set_index("Type")["Template"].to_dict()

    def build_instruction(
        self,
        property_name: str,
        model_card_text: str,
        *,
        property_question: Optional[str] = None,
    ) -> str:
        """
        Build the user instruction for one property and model card.

        Raises:
            KeyError: If property or template type is unknown.
        """
        question = property_question or self.questions[property_name]
        template_type = self.prop_template_type_map[property_name]
        template = self.templates[template_type]

        return (
            template.replace("PROPERTY_NAME", property_name)
            .replace("PROPERTY_DESCRIPTION", question)
            .replace("RETRIEVED_CONTEXT", model_card_text)
        )

    def build_property_prompt(
        self,
        property_name: str,
        model_card_text: str,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> PropertyPrompt:
        """Build a full prompt object for one property."""
        instruction = self.build_instruction(property_name, model_card_text)
        return PropertyPrompt(
            property_name=property_name,
            template_type=self.prop_template_type_map[property_name],
            question=self.questions[property_name],
            instruction=instruction,
            system_prompt=system_prompt,
        )

    def build_all_property_prompts(
        self,
        model_card_text: str,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> List[PropertyPrompt]:
        """Build prompts for all configured properties on one model card."""
        return [
            self.build_property_prompt(
                property_name,
                model_card_text,
                system_prompt=system_prompt,
            )
            for property_name in self.property_names
        ]
