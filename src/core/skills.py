"""
Project Skills Integration & Prompt `/` Slash Commands (RES-13)
==============================================================
Provides automated discovery and dynamic injection of project skills from `.agents/skills/`.
Allows prompt templates and system prompts to use slash commands (e.g., `/pixeltable`,
`/postgresql`, `/gradio`, `/hf-gradio`) to dynamically inject specialized agent rules,
domain guidelines, and operational patterns directly into LLM inference workflows.
"""

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("pipeline_tools.skills")


@dataclass
class SkillDefinition:
    name: str
    description: str
    content: str
    path: str
    slash_command: str  # e.g., "/pixeltable"

    @property
    def instructions(self) -> str:
        """Extract markdown body instructions following YAML frontmatter."""
        text = self.content.strip()
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return text


class SkillsRegistry:
    """Registry that discovers and manages skills from `.agents/skills/`."""

    _cached_skills: Optional[Dict[str, SkillDefinition]] = None

    BUILTIN_SKILLS: Dict[str, Dict[str, str]] = {
        "boost": {
            "name": "boost",
            "description": "High-rigor engineering and deep reasoning directive.",
            "instructions": (
                "# Maximum Quality & Reasoning Directive\n"
                "- Think step-by-step with deep technical rigor and multi-perspective analysis.\n"
                "- Ensure absolute consistency, full edge-case coverage, and resilient error recovery.\n"
                "- Never make unverified assumptions or truncate critical detail.\n"
                "- Adhere strictly to architectural patterns and domain standards."
            )
        }
    }

    @classmethod
    def get_search_directories(cls) -> List[Path]:
        """Return list of candidate directories containing skill definitions in priority order."""
        dirs: List[Path] = []
        # 1. Project-local .agents/skills
        cwd_dir = Path.cwd() / ".agents" / "skills"
        if cwd_dir.exists():
            dirs.append(cwd_dir.resolve())
        proj_dir = Path(__file__).parent.parent.parent / ".agents" / "skills"
        if proj_dir.exists() and proj_dir.resolve() not in dirs:
            dirs.append(proj_dir.resolve())
        # 2. User-level ~/.gemini/config/skills
        gemini_dir = Path.home() / ".gemini" / "config" / "skills"
        if gemini_dir.exists() and gemini_dir.resolve() not in dirs:
            dirs.append(gemini_dir.resolve())
        # 3. User-level ~/.agents/skills
        user_agents_dir = Path.home() / ".agents" / "skills"
        if user_agents_dir.exists() and user_agents_dir.resolve() not in dirs:
            dirs.append(user_agents_dir.resolve())
        # 4. Environment variable override
        env_skills = os.environ.get("AGENT_SKILLS_DIR")
        if env_skills:
            env_p = Path(env_skills).resolve()
            if env_p.exists() and env_p not in dirs:
                dirs.append(env_p)
        return dirs

    @classmethod
    def get_default_skills_dir(cls) -> Path:
        """Return primary default path to project .agents/skills directory."""
        dirs = cls.get_search_directories()
        return dirs[0] if dirs else Path.cwd() / ".agents" / "skills"

    @classmethod
    def discover_skills(cls, skills_dir: Optional[Path] = None, force_refresh: bool = False) -> Dict[str, SkillDefinition]:
        """Discover all skills across configured directories containing SKILL.md and built-in directives."""
        if cls._cached_skills is not None and not force_refresh and skills_dir is None:
            return cls._cached_skills

        search_dirs = [skills_dir] if skills_dir is not None else cls.get_search_directories()
        skills: Dict[str, SkillDefinition] = {}

        # 1. Register built-in directives (e.g. /boost)
        for b_name, b_info in cls.BUILTIN_SKILLS.items():
            slash_cmd = f"/{b_name}"
            skill = SkillDefinition(
                name=b_info["name"],
                description=b_info["description"],
                content=f"---\nname: {b_info['name']}\ndescription: {b_info['description']}\n---\n{b_info['instructions']}",
                path=f"builtin://{b_name}",
                slash_command=slash_cmd
            )
            skills[b_info["name"]] = skill
            skills[slash_cmd] = skill

        # 2. Discover disk skills from candidate directories
        for target_dir in search_dirs:
            if not target_dir.exists() or not target_dir.is_dir():
                continue

            for entry in target_dir.iterdir():
                if entry.is_dir():
                    skill_md = entry / "SKILL.md"
                    if skill_md.exists() and skill_md.is_file():
                        try:
                            content = skill_md.read_text(encoding="utf-8", errors="ignore")
                            name = entry.name
                            desc = ""

                            # Parse YAML frontmatter if present
                            if content.startswith("---"):
                                parts = content.split("---", 2)
                                if len(parts) >= 3:
                                    fm = parts[1]
                                    for line in fm.splitlines():
                                        if line.strip().startswith("name:"):
                                            name = line.split(":", 1)[1].strip().strip('"\'')
                                        elif line.strip().startswith("description:"):
                                            desc = line.split(":", 1)[1].strip().strip('"\'')

                            slash_cmd = f"/{name}"
                            skill = SkillDefinition(
                                name=name,
                                description=desc,
                                content=content,
                                path=str(skill_md.resolve()),
                                slash_command=slash_cmd
                            )
                            # Register both bare name and slash command if not already registered
                            if name not in skills:
                                skills[name] = skill
                            if slash_cmd not in skills:
                                skills[slash_cmd] = skill
                        except Exception as e:
                            logger.warning(f"Error loading skill from {skill_md}: {e}")

        if skills_dir is None:
            cls._cached_skills = skills
        return skills

    @classmethod
    def list_skills(cls) -> List[Dict[str, Any]]:
        """Return clean list of unique discovered skills for UI dropdowns or chips."""
        all_skills = cls.discover_skills()
        unique = {}
        for k, v in all_skills.items():
            if not k.startswith("/"):
                unique[k] = {
                    "name": v.name,
                    "slash_command": v.slash_command,
                    "description": v.description,
                    "path": v.path
                }
        return list(unique.values())

    @classmethod
    def get_slash_commands(cls) -> List[str]:
        """Return list of valid slash command strings, e.g. ['/gradio', '/pixeltable']."""
        skills = cls.discover_skills()
        return sorted(list({v.slash_command for v in skills.values()}))

    @classmethod
    def find_slash_commands(cls, text: str) -> List[str]:
        """Extract all valid standalone slash command tokens (e.g. '/pixeltable') from text, ignoring URLs and file paths."""
        if not text:
            return []
        # Matches /command when preceded by whitespace/start-of-line and followed by boundary/whitespace/punctuation
        tokens = re.findall(r"(?<![a-zA-Z0-9_\-:/])(/[a-zA-Z0-9_\-]+)(?=\s|[.,;:!?]|$)", text)
        return list(dict.fromkeys(tokens))

    @classmethod
    def expand_prompt_with_skills(
        cls,
        prompt_template: str,
        system_prompt: str = "",
        strip_command_tokens: bool = True
    ) -> Tuple[str, str, List[str]]:
        """
        Dynamically decorate and expand prompt and system prompt with discovered skills.

        Finds any `/skill` slash commands in either the user prompt template or system prompt,
        loads the corresponding `SKILL.md` instructions, injects them cleanly into the system prompt,
        and optionally strips the slash command tokens from the user prompt.

        Returns:
            (expanded_prompt, expanded_system_prompt, applied_skill_names)
        """
        skills = cls.discover_skills()
        tokens_in_user = cls.find_slash_commands(prompt_template)
        tokens_in_system = cls.find_slash_commands(system_prompt)
        all_tokens = list(dict.fromkeys(tokens_in_user + tokens_in_system))

        applied_skills: List[str] = []
        skill_injections: List[str] = []

        cleaned_user_prompt = prompt_template
        cleaned_system_prompt = system_prompt

        for token in all_tokens:
            cmd = token.lower()
            if cmd in skills:
                skill = skills[cmd]
                if skill.name not in applied_skills:
                    applied_skills.append(skill.name)
                    injection = (
                        f"\n\n---\n"
                        f"### Active Skill Guidelines: {skill.name}\n"
                        f"{skill.description}\n\n"
                        f"{skill.instructions}\n"
                        f"---\n"
                    )
                    skill_injections.append(injection)

                if strip_command_tokens:
                    # Strip the standalone slash command token cleanly without breaking URLs or trailing punctuation
                    pattern = re.compile(rf"(?<![a-zA-Z0-9_\-:/]){re.escape(token)}(?=\s|[.,;:!?]|$)\s*", re.IGNORECASE)
                    cleaned_user_prompt = pattern.sub("", cleaned_user_prompt).strip()
                    cleaned_system_prompt = pattern.sub("", cleaned_system_prompt).strip()

        # Combine skill instructions into system prompt
        if skill_injections:
            if not cleaned_system_prompt:
                cleaned_system_prompt = "You are a specialized AI assistant operating under domain skill directives."
            cleaned_system_prompt = cleaned_system_prompt.strip() + "".join(skill_injections)

        return cleaned_user_prompt, cleaned_system_prompt, applied_skills
