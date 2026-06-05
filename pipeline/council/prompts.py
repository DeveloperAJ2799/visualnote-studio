"""Round-specific prompt templates for the council.

System prompts live in ``council_config.json`` (under each member's
``system_prompt`` field) so they can be tuned without touching code.

This module builds the **user** prompt (the runtime data each member
needs to do its job) and dispatches to the right builder based on the
member's ``output_kind``. The orchestrator calls ``build_user_prompt``
and never has to know which role any specific member plays.
"""
from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .members import Member
    from .state import CouncilState, Review


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def build_user_prompt(
    member: "Member",
    state: "CouncilState",
    *,
    targets: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build the user prompt for `member` based on its ``output_kind``.

    Args:
        member: The council member being called.
        state: The full council state (doc text, prior outputs, etc.).
        targets: Only used for review members. A list of
            ``{"anon_label": "Member A", "output": {...}}`` dicts.

    Returns:
        The user-prompt string to send alongside the member's system prompt.
    """
    kind = member.output_kind
    if kind == "script":
        return scriptwriter_user(
            state.doc_text, state.doc_title_hint, state.target_minutes
        )
    if kind == "design":
        return visual_designer_user(
            state.doc_text,
            state.doc_title_hint,
            state.member_outputs.get("scriptwriter", {}),
        )
    if kind == "review":
        return review_user(member.name, targets or [], state.doc_text)
    if kind == "synthesis":
        return chairman_user(
            state.doc_text,
            state.doc_title_hint,
            state.target_minutes,
            state.member_outputs.get("scriptwriter", {}),
            state.member_outputs.get("visual_designer", {}),
            _serialize_reviews_for_chairman(state.reviews),
        )
    raise ValueError(
        f"Unknown output_kind for member {member.name!r}: {kind!r}. "
        "Valid kinds: script, design, review, synthesis."
    )


def _serialize_reviews_for_chairman(reviews: List["Review"]) -> List[Dict[str, Any]]:
    """Turn state.reviews into the plain-dict shape chairman_user expects."""
    out: List[Dict[str, Any]] = []
    for r in reviews:
        out.append(
            {
                "member": r.member,
                "target_outputs": r.target_outputs,
                "critiques": [
                    {
                        "target_member": c.target_member,
                        "scene_id": c.scene_id,
                        "verdict": c.verdict,
                        "issues": c.issues,
                        "suggested_fix": c.suggested_fix,
                    }
                    for c in r.critiques
                ],
                "overall_assessment": r.overall_assessment,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Round 1 — creators
# ---------------------------------------------------------------------------


def scriptwriter_user(
    doc_text: str,
    doc_title_hint: str,
    target_minutes: int = 10,
) -> str:
    """Round 1 prompt for the Scriptwriter (output_kind: 'script')."""
    target_scenes = max(15, target_minutes * 2)
    target_words = target_minutes * 140
    return dedent(
        f"""
        You are given the full text of a study document below. Produce a
        JSON scene manifest for a LONG-FORM deep-dive explainer video that
        runs approximately {target_minutes} minutes (around {target_scenes}
        scenes, ~{target_words} words of narration total).

        STRICT RULES:
        1. Produce between {max(15, target_scenes - 2)} and {target_scenes + 2} scenes.
        2. Each scene covers ONE coherent sub-topic in depth.
        3. Each narration must be 50-120 words, conversational, and richly
           explanatory. TEACH the concept — analogies, examples,
           step-by-step reasoning.
        4. The first scene should be a clear "title_card" introducing the
           document's big idea.
        5. The last scene should be a "title_card" with a recap.
        6. Set visual_type, manim_prompt, image_query, and html_content
           to safe defaults: visual_type="title_card", all the rest null.
           The visual designer will pick the actual styles.

        Output schema (output ONLY this JSON object, nothing else):
        {{
          "document_title": "<string>",
          "total_scenes": <int>,
          "scenes": [
            {{
              "scene_id": <int starting at 1>,
              "title": "<short descriptive title>",
              "narration": "<50-120 word deep-dive narration>",
              "duration_hint_s": <int>,
              "visual_type": "title_card",
              "manim_prompt": null,
              "image_query": null,
              "html_content": null
            }}
          ]
        }}

        Document title hint: {doc_title_hint}

        Document text:
        {doc_text}
        """
    ).strip()


def visual_designer_user(
    doc_text: str,
    doc_title_hint: str,
    scriptwriter_output: Dict[str, Any],
) -> str:
    """Round 1 prompt for the Visual Designer (output_kind: 'design')."""
    scenes_summary = _scenes_brief(scriptwriter_output)
    return dedent(
        f"""
        You are given a study document and a draft scene manifest from
        another council member. Your job is to design the VISUAL look of
        each scene. Do NOT change the narration or the scene count.

        Document title: {doc_title_hint}

        Draft scenes (from Member A — Scriptwriter):
        {scenes_summary}

        For EACH scene, pick:
        1. ``frame_style`` — one of:
           - "text_only"     → full-screen text, no diagram area
           - "image_left"    → diagram/image on left, text on right
           - "diagram_center"→ big animated diagram, caption bar at bottom
           - "split_compare" → two equal columns of comparison
           - "quote_callout" → one big quote/fact, full screen
           - "title_hero"    → just the title, huge, full screen
        2. ``diagram`` — null, OR a dict with:
           - ``primitive``: "orbit" | "molecule" | "helix" | "cell" |
             "graph_bar" | "graph_line" | "tree_hierarchy" | "cycle" |
             "flow" | "timeline" | "concept_map" | "matrix"
           - ``params``: free-form dict (e.g. {{"center":"C", "satellites":["e-","e-"]}})
        3. ``animations`` — list of {{"target": "id", "type": "orbit|pulse|draw|stagger|counter|morph|flow|progress", "duration_s": <float>}}
        4. ``highlights`` — list of 1-4 short words from the narration to pulse/glow

        Frame-style rules of thumb:
        - Use "title_hero" for the first and last scene.
        - Use "quote_callout" for a key takeaway / memorable line.
        - Use "image_left" when a real photo would help.
        - Use "diagram_center" for atoms, molecules, cells — anything the viewer must SEE.
        - Use "split_compare" for "X vs Y" content.
        - Use "text_only" for pure definitions or recaps.

        Output schema (output ONLY this JSON object, nothing else):
        {{
          "document_title": "<string>",
          "scene_designs": [
            {{
              "scene_id": <int>,
              "frame_style": "<one of the 6 above>",
              "diagram": null | {{"primitive": "<one of 12>", "params": {{}} }},
              "animations": [<list>],
              "highlights": [<list>],
              "rationale": "<1-2 sentences: why this fits the scene>"
            }}
          ]
        }}

        Document text (for context — do not paraphrase):
        {doc_text[:8000]}
        """
    ).strip()


# ---------------------------------------------------------------------------
# Round 2 — peer reviews (anonymized)
# ---------------------------------------------------------------------------


def review_user(
    reviewer_name: str,
    targets: List[Dict[str, Any]],  # list of {"anon_label": "Member A", "output": {...}}
    doc_text: str,
) -> str:
    """Round 2 prompt template. ``reviewer_name`` selects the rubric."""
    rubric = _review_rubric(reviewer_name)
    targets_text = _format_targets_for_review(targets)
    return dedent(
        f"""
        You are reviewing the work of OTHER council members. You see their
        outputs labeled anonymously (Member A, Member B, etc.) so you can
        focus on the work, not the author.

        Your rubric (your specific concern):
        {rubric}

        Source document (for grounding):
        {doc_text[:12000]}

        Outputs to review:
        {targets_text}

        For each scene in Member A's narration AND each scene in Member B's
        design, produce a critique. Use the following JSON schema (output
        ONLY this object, nothing else):

        {{
          "reviews": [
            {{
              "target_member": "Member A" | "Member B",
              "scene_id": <int>,
              "verdict": "approve" | "concern" | "reject",
              "issues": ["<short issue>", ...],
              "suggested_fix": "<how to fix, or empty if approve>"
            }}
          ],
          "overall_assessment": "<2-4 sentence summary of the work>"
        }}
        """
    ).strip()


def _review_rubric(reviewer_name: str) -> str:
    if reviewer_name == "fact_checker":
        return dedent(
            """
            You verify FACTS. For every concrete claim in Member A's
            narration (numbers, names, definitions, "all X do Y" claims,
            chemical/biological facts), find the supporting paragraph in
            the source document above. If you cannot find it, mark
            "verdict": "reject" and explain what is unverified.

            Be ruthless. False confidence is worse than false doubt.
            Only mark "approve" if the claim is well-supported.
            """
        ).strip()
    if reviewer_name == "pedagogy_reviewer":
        return dedent(
            """
            You evaluate TEACHING QUALITY. For each scene, check:
            - Pacing: 50-120 words? Too long? Too short?
            - Self-containment: does the scene stand alone, or does it
              assume knowledge from a previous scene that was never
              introduced?
            - Jargon: are technical terms defined on first use?
            - Flow: does scene N+1 build naturally on scene N?
            - Visual fit (Member B): does the frame style match what the
              narration is actually explaining?

            Mark "approve" if the scene teaches well. "concern" for
            small fixable issues. "reject" only for fundamental problems.
            """
        ).strip()
    # scriptwriter or visual_designer reviewing the other
    if reviewer_name == "scriptwriter":
        return dedent(
            """
            You wrote the script (narration). Now review the VISUAL
            DESIGNER's design choices for each scene. For each scene:
            - Does the chosen frame_style fit what the narration is
              teaching?
            - Is the diagram primitive (if any) appropriate?
            - Are the animations well-targeted, or do they distract?
            - Are the highlighted words the right words to emphasize?

            Mark "approve" if the visuals serve the narration. "concern"
            for mismatches. "reject" only if the visual actively
            contradicts the script.
            """
        ).strip()
    if reviewer_name == "visual_designer":
        return dedent(
            """
            You designed the visuals. Now review the SCRIPTWRITER's script
            for visual fit. For each scene:
            - Is the title accurate and short (≤ 8 words)?
            - Does the narration describe something the viewer can SEE,
              or is it abstract?
            - Does the scene's purpose match its visual_type placeholder
              (currently all "title_card" — that's fine; the chairman
              will merge)?

            Mark "approve" if the script gives the visual designer
            something concrete to illustrate. "concern" if the script
            is too abstract to visualize. "reject" only if the script
            is fundamentally wrong.
            """
        ).strip()
    return "Review the work and return JSON."


def _format_targets_for_review(targets: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for t in targets:
        label = t.get("anon_label", "Member ?")
        output = t.get("output", {})
        parts.append(f"=== {label} OUTPUT ===")
        parts.append(_safe_json(output))
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Round 3 — chairman synthesis
# ---------------------------------------------------------------------------


def chairman_user(
    doc_text: str,
    doc_title_hint: str,
    target_minutes: int,
    scriptwriter_output: Dict[str, Any],
    visual_designer_output: Dict[str, Any],
    reviews: List[Dict[str, Any]],
) -> str:
    """Round 3 prompt: the chairman reads everything and produces the final manifest."""
    target_scenes = max(15, target_minutes * 2)
    return dedent(
        f"""
        You are the editor-in-chief of a 5-member council. You must
        produce the FINAL scene manifest for a {target_minutes}-minute
        explainer video (~{target_scenes} scenes).

        You have:
        1. A draft script from the Scriptwriter (Member A)
        2. A draft visual design from the Visual Designer (Member B)
        3. Reviews from the Fact-Checker (Member C) and the Pedagogy
           Reviewer (Member D)
        4. The source document

        Document title: {doc_title_hint}
        Target: {target_minutes} minutes, ~{target_scenes} scenes

        Source document (for grounding):
        {doc_text[:12000]}

        === Member A — SCRIPTWRITER (draft scenes) ===
        {_safe_json(scriptwriter_output)}

        === Member B — VISUAL DESIGNER (draft designs) ===
        {_safe_json(visual_designer_output)}

        === Member C — FACT-CHECKER review ===
        {_safe_json(_find_review(reviews, "fact_checker"))}

        === Member D — PEDAGOGY REVIEWER review ===
        {_safe_json(_find_review(reviews, "pedagogy_reviewer"))}

        YOUR JOB:
        1. Merge Member A's script with Member B's design: for every scene,
           combine the title/narration from A with the frame_style /
           diagram / animations from B.
        2. For each scene, set a confidence score 0.0-1.0 based on the
           reviewers' verdicts (approve ≈ 0.9, concern ≈ 0.7, reject ≈ 0.4).
        3. Set ``visual_type`` based on the chosen frame_style:
           - text_only, quote_callout, title_hero → "title_card"
           - image_left, diagram_center, split_compare → "manim_animation"
             (or "mixed" if the diagram primitive requires HTML/photo)
        4. If a reviewer's "reject" verdict is overruled, mark
           ``chairman_override: true`` and record the original concern in
           the dissent summary.
        5. Set ``low_confidence: true`` on any scene with confidence < 0.6.
        6. Write a plain-English ``dissent_summary`` (1-3 sentences) that
           notes any overruled rejections, any unfixable concerns, and the
           overall confidence of the manifest.

        Output schema (output ONLY this JSON object, nothing else):
        {{
          "document_title": "<string>",
          "total_scenes": <int>,
          "scenes": [
            {{
              "scene_id": <int>,
              "title": "<string>",
              "narration": "<string>",
              "duration_hint_s": <int>,
              "visual_type": "<title_card|manim_animation|html_frame|image_overlay|mixed>",
              "manim_prompt": "<string or null>",
              "image_query": "<string or null>",
              "html_content": "<string or null>",
              "frame_style": "<text_only|image_left|diagram_center|split_compare|quote_callout|title_hero>",
              "diagram": null | {{"primitive": "<str>", "params": {{}} }},
              "animations": [<list>],
              "highlights": [<list>],
              "confidence": <float 0-1>,
              "low_confidence": <bool>,
              "chairman_override": <bool>
            }}
          ],
          "dissent_summary": "<plain-English 1-3 sentences>",
          "confidence_overall": <float 0-1>
        }}
        """
    ).strip()


# ---------------------------------------------------------------------------
# Mock prompts (for tests and offline mode)
# ---------------------------------------------------------------------------


def mock_round1_user(role: str, doc_title_hint: str) -> str:
    return f"[MOCK] Generate a {role} JSON output for document '{doc_title_hint}'."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scenes_brief(scriptwriter_output: Dict[str, Any]) -> str:
    """Render a compact summary of scriptwriter output for the designer's prompt."""
    lines: List[str] = []
    for s in scriptwriter_output.get("scenes", []):
        sid = s.get("scene_id")
        title = s.get("title", "")
        narr = s.get("narration", "")
        lines.append(f"Scene {sid}: {title}\n  Narration: {narr[:280]}{'...' if len(narr) > 280 else ''}")
    return "\n\n".join(lines)


def _find_review(reviews: List[Dict[str, Any]], member_name: str) -> Dict[str, Any]:
    for r in reviews:
        if r.get("member") == member_name:
            return r
    return {}


def _safe_json(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(obj)
