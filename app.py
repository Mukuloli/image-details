import os
import json
import base64
import io
import re
import traceback

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from google import genai
from google.genai import types
from PIL import Image

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- Safe Gemini client initialization ---
_api_key = os.getenv("GEMINI_API_KEY")
client = None
if _api_key:
    try:
        client = genai.Client(api_key=_api_key)
        print(f"[INIT] Gemini client initialized successfully.")
    except Exception as e:
        print(f"[INIT] WARNING: Failed to initialize Gemini client: {e}")
else:
    print("[INIT] WARNING: GEMINI_API_KEY not set. API routes will not work.")

# ---------------------------------------------------------------------------
# Agentic Vision Module — Extracts structured details from an image
# ---------------------------------------------------------------------------

VISION_PROMPT = """You are an ELITE visual analyst with pixel-level precision in fashion, textiles,
jewelry, color science, and garment construction. Your output will be fed DIRECTLY into an
AI image-generation model to PERFECTLY RECREATE this exact clothing, jewelry, and styling
on a different person. Every missing or inaccurate detail = a visible flaw in the output image.

## ━━━ YOUR #1 MISSION ━━━
**DRESS and JEWELRY are your TOP PRIORITY.** The generation model needs to reproduce the
exact same dress/outfit and exact same jewelry on another person. If you miss any dress detail
or jewelry detail, the output will look WRONG. Focus 80% of your effort on DRESS + JEWELRY.

## ━━━ ABSOLUTE RULES (NEVER VIOLATE) ━━━
1. **EXACT COLORS**: Every color MUST have BOTH a precise name AND HEX code.
   Example: "Deep burgundy wine (#722F37)". ALL colors — primary, secondary, accent,
   trim, thread, lining, stone, metal — without exception.
2. **PRECISE COUNTING**: Count ONE BY ONE. NEVER use "some", "several", "many", "a few",
   "multiple", or "various". Give EXACT numbers or "approximately N (estimated)".
3. **ZERO SKIP POLICY**: If a detail exists — no matter how small — it MUST appear.
   A tiny thread, a micro-print, a subtle stitch = MUST BE DESCRIBED.
4. **NO HALLUCINATION**: Only what is visually confirmed. Uncertain → prefix "appears to be".
5. **SPATIAL PRECISION**: WHERE each element is — "center-front", "left shoulder",
   "3cm below collar", "along hemline", "at waistline".

## ━━━ ANALYSIS PROTOCOL ━━━

### STEP 1: OVERVIEW
- Garment type, overall silhouette, style era/category.
- Person's pose and body angle (affects garment visibility).

### ★★★ STEP 2: DRESS DEEP ANALYSIS (MOST CRITICAL — SPEND MAXIMUM TIME HERE) ★★★
**This step determines whether the generated image will look like the REAL dress or a FAKE one.**

#### 2A: DRESS IDENTITY
- Exact garment type and sub-type (e.g., "Anarkali kurta with floor-length flare", "A-line midi dress with wrap front")
- Overall shape/silhouette from shoulder to hem — HOW does it flow on the body?
- Style category: traditional/western/fusion/ethnic/formal/casual
- What makes THIS dress visually DISTINCT from other similar dresses?

#### 2B: DRESS COLORS (REGION-BY-REGION)
- Scan the dress in regions: neckline area, chest/bodice, waist, hip area, skirt/lower half, sleeves (L+R), back (if visible), hem
- For EACH region: exact color name + HEX code
- Color in LIGHT areas (HEX) vs color in SHADOW areas (HEX)
- Any gradients, ombré, color transitions → start HEX → end HEX
- Any color contrast between different parts of the dress

#### 2C: DRESS FABRIC & TEXTURE
- Fabric type with confidence % (silk, cotton, chiffon, georgette, velvet, net, brocade, satin, crepe, etc.)
- Surface: matte/glossy/semi-sheer/rough/smooth/ribbed/textured
- Fabric weight: lightweight/medium/heavy — how it drapes and falls
- Transparency: opaque/semi-sheer/sheer — can you see skin through it?
- Fabric sheen: does it reflect light? Where and how much?
- Weave pattern if visible: plain, twill, satin, jacquard, brocade

#### 2D: DRESS CONSTRUCTION & STRUCTURE
- **Neckline**: Exact type (V-neck, round, sweetheart, boat, square, mandarin, keyhole, etc.), depth measurement, width, any collar/stand
- **Sleeves**: Type (full/3-quarter/half/cap/sleeveless/puff/bell/bishop), length, width at opening, cuff style, any detailing on sleeves
- **Bodice**: Fitted/loose, any darts, boning, shirring, gathering, pleating at bodice
- **Waistline**: Natural/empire/drop/no waistline, any belt/tie/cinch at waist
- **Skirt/Lower half**: Flare type (A-line/circle/straight/mermaid/pleated/layered), fullness, number of layers
- **Length**: Exact length relative to body (above knee/knee/below knee/midi/ankle/floor)
- **Hemline**: Straight/curved/asymmetric/high-low, hem finishing
- **Panels**: Count of fabric panels, their shapes and arrangement
- **Seams**: All visible seams — type (French/flat-fell/princess/side), position
- **Pleats**: Type (box/knife/accordion/inverted), count, position, width
- **Closures**: Zip (position), hooks, ties, buttons — count, type, position
- **Buttons**: EXACT count, diameter, shape, material, color+HEX, spacing between each
- **Pockets**: Count, type (patch/welt/hidden), position, size
- **Slits/Vents**: Count, position, length
- **Lining**: Visible? Color+HEX, fabric type

#### 2E: DRESS PATTERN & PRINT
- Pattern type: solid/striped/plaid/floral/geometric/abstract/paisley/block-print/bandhani/ikat/etc.
- If patterned: motif SHAPE, exact SIZE, all COLORS (each with HEX), spacing between motifs, orientation, repeat pattern
- Pattern alignment at seams: matched/offset/random
- Print technique: screen-printed/digital/woven-in/embroidered/block-printed/hand-painted
- Border prints: any different pattern/design at hemline, neckline, or sleeve edges

#### 2F: DRESS EMBELLISHMENTS & DECORATION
- **Embroidery**: Thread colors (ALL HEX codes), stitch types (satin/chain/cross/zari/aari/resham), motif shapes, coverage area on dress, density
- **Beadwork**: EXACT count of beads, bead material, color+HEX, size, arrangement pattern, where on dress
- **Sequins**: EXACT count (or area covered), color+HEX, size, shape, arrangement
- **Stone/crystal work**: Count, type (kundan/rhinestone/crystal), color+HEX, size, setting
- **Mirror work (shisha)**: Count, size, shape, arrangement, border thread color+HEX
- **Zari/metallic work**: Gold/silver, thread type, coverage area, motif patterns
- **Lace**: Type (Chantilly/guipure/crochet), color+HEX, width, position on dress
- **Appliqué/patchwork**: Fabric type, color+HEX, shape, position
- **Ribbon/tape**: Width, color+HEX, position, how attached
- **Tassels/pom-poms/fringe**: Count, size, color+HEX, position
- **Ruffles/frills**: Layer count, width, position, fabric type

#### 2G: DRESS SPECIAL FEATURES (WHAT MAKES IT UNIQUE)
- **Piping/edging**: Contrast piping, bias tape, satin edging — color+HEX, position
- **Trim/borders**: Decorative borders at hem/cuffs/neckline — full description
- **Topstitching**: Decorative stitching, contrast thread — color+HEX
- **Cutwork/laser-cut**: Cut-out patterns, their shapes, positions
- **Wrap/overlap**: How fabric wraps, direction, overlap amount
- **Asymmetric elements**: Any left-right differences
- **Tie/drawstring details**: Position, material, length, tassels at ends
- **Dupatta/scarf attached**: Is there an attached drape? Detail it fully
- **Hidden details**: Inner collar, peek of lining, underside details visible

### ★★★ STEP 3: JEWELRY DEEP ANALYSIS (SECOND MOST CRITICAL) ★★★
**Every piece of jewelry must be described so precisely that the generation model can recreate it exactly.**

For EACH piece of jewelry visible, provide:

#### 3A: NECKLACE/CHAIN (if present)
- Type: choker/princess/matinee/opera/pendant/statement/layered/mangalsutra/haar
- Metal: gold/silver/rose gold/oxidized/kundan — exact finish (polished/matte/antique/brushed)
- Metal color HEX code
- Chain: link style (cable/box/rope/snake/curb), thickness, length
- Pendant (if any): shape, size, design, material, color+HEX
- Stones: EXACT count per section, stone type (diamond/ruby/emerald/pearl/kundan/polki/AD), cut (round/oval/marquise/pear/cabochon), EXACT color+HEX for each stone color, size, setting type (prong/bezel/pave/channel), arrangement pattern
- Beads: count, material, color+HEX, size, spacing
- Design elements: filigree, meenakari (enamel colors+HEX), engravings, motifs
- Dangling elements: drops, jhumka, tassels — count, shape, material
- Total dimensions: length, width at widest point

#### 3B: EARRINGS (if present)
- Type: stud/drop/chandelier/jhumka/bali/huggie/hoop/ear cuff
- Metal type + finish + color HEX
- Main body: shape, size, design
- Stones: count, type, color+HEX, size, arrangement
- Dangling elements: length, movement, what hangs (pearls/chains/beads)
- Total drop length from earlobe

#### 3C: BANGLES/BRACELETS (if present)
- Count of bangles — EXACT number on each wrist
- Type: bangle/kangan/cuff/bracelet/kada
- Material: gold/glass/lac/metal — finish and color+HEX
- Width of each bangle, thickness
- Stones/embellishments on bangles: count, type, color+HEX
- Pattern on bangles: plain/engraved/enameled/stone-studded
- Arrangement: tight stack, loose, mixed colors

#### 3D: RINGS (if present)
- Count, which fingers
- Metal type + color HEX
- Stone: type, count, color+HEX, setting
- Band style: thin/thick/twisted/engraved

#### 3E: MAANG TIKKA / HEAD JEWELRY (if present)
- Chain length, where it sits on hair parting
- Central pendant: shape, size, stones, color+HEX
- Side attachments: how it connects to hair/ears

#### 3F: ANKLETS / WAIST CHAIN / OTHER JEWELRY
- Full description with all details as above

#### 3G: NOSE RING/PIN (if present)
- Type: stud/ring/nath, size, which nostril
- Metal + stone details with colors+HEX
- Chain attached (if nath): length, attachment point

### STEP 4: ACCESSORIES
- Belt, scarf/dupatta, watch, bag, sunglasses, hair accessories, footwear.
- All with full color+hex descriptions.

### STEP 5: FIT & DRAPE
- Fit: tight/fitted/relaxed/oversized/draped.
- Where it clings vs where it falls loose.
- Count major fold lines and their direction.
- Garment length relative to body landmarks.

### STEP 6: ENVIRONMENT & LIGHTING
- Light source direction, intensity, temperature (warm/cool/neutral).
- Shadow patterns on garment. Background colors + hex.

### STEP 7: FINAL CROSS-VERIFICATION
- Re-scan the ENTIRE image one final time.
- Did you miss ANY dress detail? Any embroidery motif? Any stitch?
- Did you miss ANY jewelry piece? Any stone? Any bead? Any chain link detail?
- Verify all counts. Confirm all hex codes.
- Ask yourself: "Can someone recreate this EXACT dress and jewelry from my description alone?" If NO → add more details.

## ━━━ OUTPUT FORMAT ━━━

Return a valid JSON object with these fields (null if not applicable):

{
  "dress_type": "EXACT garment type with full sub-category (e.g. 'Anarkali kurta with floor-length flare and attached dupatta')",
  "dress_identity": "One paragraph describing the COMPLETE visual identity of the dress — what someone would see at first glance, what makes it recognizable, its overall vibe",
  "style_era": "Style period/aesthetic",
  "primary_color": "Exact shade name + hex code",
  "primary_color_hex": "#hex only",
  "secondary_colors": [{"name": "Color", "hex": "#hex", "location": "Where on dress"}],
  "accent_colors": [{"name": "Color", "hex": "#hex", "location": "Where on dress"}],
  "color_in_shadows": "Primary color in shadow — name + hex",
  "color_in_highlights": "Primary color in highlights — name + hex",
  "color_variations_by_region": "How color differs across dress regions — each with hex",
  "fabric": "Fabric type + confidence %",
  "fabric_weight": "Weight + drape behavior",
  "fabric_sheen": "How the fabric reflects light — where shiny, where matte",
  "texture": "Surface texture description",
  "texture_detail": "Micro-level texture: thread, weave, sheen, irregularities",
  "transparency": "Opaque / Semi-sheer / Sheer",
  "neckline": "EXACT type, depth, width, collar stand height, any neckline embellishment",
  "sleeves": "Type, length, width, shape, cuff style, cuff closure, any sleeve embellishment",
  "bodice": "Fitted/loose, darts, boning, gathering, any bodice-specific details",
  "waistline": "Type, any belt/tie/cinch, how defined",
  "skirt_lower": "Flare type, fullness, layers, how it falls",
  "length": "Garment length relative to body",
  "hemline": "Hem style + finish + any hem decoration",
  "silhouette": "Overall garment shape from shoulder to hem",
  "fit": "Fit style + drape description",
  "fit_on_body": "Where clings, where loose, how falls",
  "pattern": "Pattern type",
  "pattern_details": "Full description: motif SHAPE, SIZE, SPACING, ORIENTATION, repeat count, arrangement",
  "pattern_colors": [{"name": "Color", "hex": "#hex", "role": "background/motif/outline/border"}],
  "pattern_alignment": "How pattern aligns at seams",
  "border_design": "Any decorative border at hem/neckline/sleeves — full description with colors+HEX",
  "buttons": "EXACT count, diameter, shape, material, color+hex, holes, spacing, positions",
  "buttonholes": "Count, style, thread color+hex",
  "closures": "Each closure: type, count, position, material, color+hex",
  "pockets": "Count, type, position, size",
  "vents_and_slits": "Count, position, length",
  "structural_details": "ALL panels (count), darts (count+position), pleats (type+count+position), tucks, gathers — comprehensive",
  "seams_and_stitching": "Seam types, topstitching, stitch width, thread color+hex",
  "lining_visible": "Lining color+hex + fabric if visible",
  "embroidery": "COMPLETE embroidery description — thread colors (ALL HEX), stitch types, motif shapes, motif sizes, coverage area, density, placement on dress",
  "beadwork": "Bead/sequin/stone work on dress — exact counts, materials, colors+HEX, sizes, arrangement, placement",
  "embellishments": "ALL other decorative elements — lace, ribbon, appliqué, mirror work, zari, fringe, tassels — each with count, color+HEX, position, size",
  "special_design_features": "ALL unique design elements — piping, trim, borders, contrast edging, cutwork, wrap details, asymmetric elements, drawstrings, ties, belt loops, tabs. EACH with position, color+hex, size",
  "micro_details": "TINY details — small prints within prints, subtle stitches, barely visible embroidery, miniature buttons, hidden snaps, contrast thread, edge finishing, hem tape, brand labels, monograms, tiny beads",
  "design_dna": "WHAT makes THIS dress DIFFERENT from a plain/generic version? List EVERY distinctive feature",
  "dress_reproduction_checklist": "A numbered checklist of the TOP 10 most important visual features someone MUST get right to reproduce this exact dress",
  "jewelry_pieces": [
    {
      "type": "Exact jewelry type (e.g. 'kundan choker necklace', 'gold jhumka earrings', 'glass bangles set')",
      "material": "Metal/material type + finish (e.g. 'antique gold with polished finish')",
      "material_color_hex": "#hex",
      "stones": "EXACT count per stone type, cut shape, color+HEX for each, size in mm, setting type, arrangement pattern",
      "pearls": "Count, size, color+HEX, real/faux, arrangement",
      "enamel_meenakari": "Enamel work colors (each HEX), patterns, coverage",
      "chain_details": "Link shape, count if countable, thickness, pattern",
      "design_elements": "Filigree, engravings, motifs, dots, texturing — full description",
      "dangling_elements": "What hangs: drops/jhumka/tassels/chains — count, length, material, color+HEX",
      "dimensions": "Length, width, drop length",
      "position_on_body": "Exact placement",
      "visual_weight": "Light/medium/heavy/statement",
      "description": "Complete one-paragraph description that could recreate this piece"
    }
  ],
  "jewelry_reproduction_checklist": "A numbered checklist of the TOP 5 most important visual features someone MUST get right to reproduce the exact jewelry",
  "accessories": "Every non-jewelry accessory with full details + colors+hex",
  "layering": "Layer count, each layer described with fabric + color",
  "proportions": "Key proportional relationships",
  "draping_and_folds": "COUNT of fold lines, direction, depth, where fabric bunches",
  "garment_condition": "New/worn/wrinkled/crisp/pressed",
  "lighting": "Light direction, intensity, type, color temperature",
  "shadows_on_garment": "Where shadows fall, intensity, color+hex",
  "pose": "Subject pose, body angle, how it affects garment visibility",
  "background": "Background description with colors+hex",
  "overall_style": "Style category / aesthetic",
  "counted_elements_summary": "FINAL count of EVERY countable element with color+hex. Format: 'N x element (color #hex)'",
  "reproduction_notes": "Critical notes for perfect reproduction — asymmetries, unusual construction, hidden details, unique characteristics"
}

## ━━━ CRITICAL OUTPUT RULES ━━━
- Return ONLY the JSON object. No markdown fences. No text before or after.
- EVERY color mention MUST have a hex code — no exceptions.
- Use code_execution tool for precise counting if needed.
- Count one-by-one. Do not round. Exact numbers or "approximately N (estimated)".
- The `dress_reproduction_checklist` and `jewelry_reproduction_checklist` fields are MANDATORY.
  These are what the generation model will use as its primary reference.
- `embroidery`, `beadwork`, `embellishments`, and `special_design_features` fields must be
  COMPREHENSIVE. If the dress has any of these, describe them in extreme detail.
- `jewelry_pieces` array must contain a SEPARATE entry for EACH visible jewelry piece.
  Do NOT combine multiple pieces into one entry.
- Your description must be so detailed that someone who has NEVER seen this image could
  instruct an AI model to generate a pixel-perfect recreation of the dress AND jewelry.
"""


def _parse_json_response(raw_text: str) -> dict:
    """Parse JSON from model response, stripping markdown fences if present."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
    return json.loads(raw_text)


REFINEMENT_PROMPT = """You are reviewing your own analysis of a clothing image. Your first pass
analysis is shown below, but it has GAPS and MISSING DETAILS.

## YOUR FIRST PASS RESULT:
{first_pass_json}

## YOUR TASK NOW:
Look at the image AGAIN very carefully. Focus on what you MISSED in the first pass.

1. **DRESS DETAILS — Did you capture EVERYTHING?**
   - `dress_identity` — one paragraph that fully describes the dress's visual identity
   - `neckline` — exact type, depth, any embellishment at neckline
   - `sleeves` — type, length, cuff details, any sleeve decoration
   - `bodice` — fitting, darts, gathering details
   - `waistline` — how is the waist defined?
   - `skirt_lower` — flare, layers, fullness
   - `embroidery` — thread colors (HEX), stitch types, motif shapes, coverage area
   - `beadwork` — exact counts, colors, arrangement
   - `border_design` — any decorative borders at hem/neckline/sleeves
   - `special_design_features` — piping, trim, cutwork, ties, wraps
   - `design_dna` — what makes THIS dress unique
   - `dress_reproduction_checklist` — top 10 features to reproduce this dress

2. **JEWELRY — Did you capture EVERY piece?**
   - `jewelry_pieces` — is there a SEPARATE entry for EACH piece?
   - Did you describe stones (exact count, color+HEX, setting)?
   - Did you describe chain details, dangling elements, enamel work?
   - `jewelry_reproduction_checklist` — top 5 features to reproduce the jewelry

3. **COLORS** — Are all HEX codes accurate? Re-verify.
4. **COUNTS** — Are button/stone/bead/bangle counts correct? Count again.

## OUTPUT:
Return a JSON object with ONLY the fields you are updating or adding.
Do NOT repeat fields that are already correct and complete in the first pass.
Only include fields where you have NEW or BETTER information.
Return ONLY the JSON. No markdown fences. No text before or after.
"""


def analyze_image(image_bytes: bytes, mime_type: str) -> dict:
    """Two-pass analysis: full scan + detail refinement for 100% detail capture."""
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    # ─── PASS 1: Full comprehensive analysis ───
    print("[VISION] Pass 1: Full comprehensive analysis...")
    response1 = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[image_part, VISION_PROMPT],
        config=types.GenerateContentConfig(
            tools=[types.Tool(code_execution=types.ToolCodeExecution)]
        ),
    )
    pass1_result = _parse_json_response(response1.text)
    print(f"[VISION] Pass 1 complete. Got {len(pass1_result)} fields.")

    # ─── Check if refinement is needed ───
    weak_fields = []
    critical_fields = [
        "dress_identity", "dress_reproduction_checklist",
        "embroidery", "beadwork", "embellishments",
        "special_design_features", "micro_details", "design_dna",
        "border_design", "neckline", "sleeves", "bodice",
        "jewelry_pieces", "jewelry_reproduction_checklist",
        "pattern_details", "structural_details",
        "buttons", "closures", "reproduction_notes",
    ]
    for field in critical_fields:
        val = pass1_result.get(field)
        if not val or str(val).lower() in ("null", "none", "n/a", ""):
            weak_fields.append(field)

    if not weak_fields:
        print("[VISION] All critical fields filled. Skipping Pass 2.")
        return pass1_result

    print(f"[VISION] Pass 2: Refining {len(weak_fields)} weak fields: {weak_fields}")

    # ─── PASS 2: Focused refinement ───
    refinement_prompt = REFINEMENT_PROMPT.format(
        first_pass_json=json.dumps(pass1_result, indent=2, ensure_ascii=False)
    )

    response2 = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[image_part, refinement_prompt],
        config=types.GenerateContentConfig(
            tools=[types.Tool(code_execution=types.ToolCodeExecution)]
        ),
    )

    try:
        pass2_result = _parse_json_response(response2.text)
        print(f"[VISION] Pass 2 complete. Got {len(pass2_result)} updated fields.")

        # Merge: Pass 2 overwrites null/empty fields from Pass 1
        for key, value in pass2_result.items():
            if value and str(value).lower() not in ("null", "none", "n/a", ""):
                existing = pass1_result.get(key)
                if not existing or str(existing).lower() in ("null", "none", "n/a", ""):
                    pass1_result[key] = value
                elif isinstance(value, str) and isinstance(existing, str) and len(value) > len(existing):
                    # Pass 2 has more detail — use it
                    pass1_result[key] = value

    except (json.JSONDecodeError, Exception) as e:
        print(f"[VISION] Pass 2 parse failed ({e}), using Pass 1 only.")

    return pass1_result


# ---------------------------------------------------------------------------
# Detail Mapping Layer — Converts structured JSON into a CONCISE visual prompt
# ---------------------------------------------------------------------------



def build_generation_prompt(details: dict, user_instructions: str = "") -> str:
    """Build a generation prompt focused on DRESS and JEWELRY reproduction.
    
    Extracts key dress and jewelry fields from the JSON and highlights them
    separately, then includes the full JSON for completeness.
    """
    dress = details.get("dress_type") or "clothing"
    primary = details.get("primary_color") or "as described"
    dress_identity = details.get("dress_identity") or ""
    
    # Extract dress-critical fields into a focused block
    dress_fields = [
        "neckline", "sleeves", "bodice", "waistline", "skirt_lower", "length",
        "hemline", "silhouette", "fit", "fabric", "fabric_sheen", "pattern",
        "pattern_details", "border_design", "embroidery", "beadwork",
        "embellishments", "special_design_features", "design_dna",
        "dress_reproduction_checklist"
    ]
    dress_block_lines = []
    for field in dress_fields:
        val = details.get(field)
        if val and str(val).lower() not in ("null", "none", "n/a", ""):
            label = field.replace("_", " ").title()
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            dress_block_lines.append(f"• {label}: {val}")
    dress_block = "\n".join(dress_block_lines) if dress_block_lines else "See full JSON below."
    
    # Extract jewelry into a focused block
    jewelry_pieces = details.get("jewelry_pieces") or []
    jewelry_checklist = details.get("jewelry_reproduction_checklist") or ""
    jewelry_block = ""
    if jewelry_pieces:
        jewelry_lines = []
        for i, piece in enumerate(jewelry_pieces, 1):
            if isinstance(piece, dict):
                desc = piece.get("description") or json.dumps(piece, ensure_ascii=False)
                ptype = piece.get("type", "Jewelry piece")
                jewelry_lines.append(f"  {i}. {ptype}: {desc}")
            else:
                jewelry_lines.append(f"  {i}. {piece}")
        jewelry_block = "\n".join(jewelry_lines)
        if jewelry_checklist:
            jewelry_block += f"\n\n  REPRODUCTION CHECKLIST:\n  {jewelry_checklist}"
    else:
        jewelry_block = "No jewelry detected — do NOT add any jewelry."
    
    # Full JSON for completeness
    full_json = json.dumps(details, indent=2, ensure_ascii=False)
    
    # User instructions block
    user_block = ""
    if user_instructions and user_instructions.strip():
        user_block = f"""\n
═══ USER'S CUSTOM INSTRUCTIONS (HIGH PRIORITY — FOLLOW EXACTLY) ═══
{user_instructions.strip()}

The above instructions from the user MUST be followed. They take priority
over default assumptions about background, lighting, pose adjustments, etc."""
    
    prompt = f"""COPY the EXACT outfit and jewelry from IMAGE 1 onto the person in IMAGE 2.
Use IMAGE 1 as your PRIMARY VISUAL REFERENCE. The text below provides additional precision.

═══ DRESS IDENTITY ═══
Type: {dress}
Primary Color: {primary}
{('Description: ' + dress_identity) if dress_identity else ''}

═══ ★ DRESS DETAILS — MATCH IMAGE 1 EXACTLY ★ ═══
{dress_block}

═══ ★ JEWELRY — MATCH IMAGE 1 EXACTLY ★ ═══
{jewelry_block}

═══ FULL CLOTHING+JEWELRY JSON (SUPPORTING REFERENCE) ═══
{full_json}

═══ CRITICAL PRIORITIES ═══
1. IMAGE 1 IS THE TRUTH: The source image is your #1 reference. Copy it visually.
2. DRESS: Match EXACT colors, pattern, embroidery, beadwork, embellishments, neckline,
   sleeves, silhouette, and length AS SEEN IN IMAGE 1.
3. JEWELRY: Reproduce every piece with correct metal color, stone colors,
   stone count, chain style, and exact placement AS SEEN IN IMAGE 1.
4. The "dress_reproduction_checklist" and "jewelry_reproduction_checklist" fields list
   the MOST IMPORTANT features — verify these against IMAGE 1.
5. Every detail must match what is VISIBLE in IMAGE 1.
{user_block}

═══ ABSOLUTE RULES ═══
• Keep the person's FACE, SKIN, HAIR, BODY, and POSE 100% UNCHANGED.
• Keep the BACKGROUND and LIGHTING exactly the same (unless user instructions say otherwise).
• ONLY change their clothing and jewelry to match IMAGE 1.
• The dress must look naturally worn — proper fit, draping, and realistic shadows.
• Jewelry must look realistic — proper reflections, weight, placement.
• The result MUST be photorealistic — like a real high-quality photograph.
• Do NOT simplify the dress or skip any embellishment detail visible in IMAGE 1."""

    return prompt


# ---------------------------------------------------------------------------
# System instruction for the generation model
# ---------------------------------------------------------------------------

GENERATION_SYSTEM_INSTRUCTION = (
    "You are an expert virtual try-on / clothing swap AI. "
    "\n\nYOU WILL RECEIVE: "
    "1) A photo of a PERSON (the target) "
    "2) A photo showing a CLOTHING OUTFIT (the reference) "
    "3) A detailed text description of the outfit "
    "\n\nYOUR TASK: "
    "Edit the PERSON's photo so they are wearing the OUTFIT from the reference photo. "
    "\n\n⚠️ CRITICAL — DO NOT MERGE IMAGES: "
    "• Your output must show EXACTLY ONE PERSON — the person from the target photo. "
    "• Do NOT overlay, blend, combine, or stack the two images together. "
    "• Do NOT show the reference person's face or body in the output. "
    "• IGNORE the person in the reference photo — only look at their CLOTHING and JEWELRY. "
    "\n\nWHAT TO KEEP FROM THE TARGET PHOTO (do NOT change these): "
    "• Face, skin color, hair, body shape, pose — 100% identical "
    "• Background, lighting, camera angle — exactly the same "
    "\n\nWHAT TO CHANGE (copy from the reference photo): "
    "• Clothing — exact same dress/outfit with all details: colors, pattern, embroidery, "
    "  beadwork, embellishments, neckline, sleeves, silhouette, length "
    "• Jewelry — every piece with correct metal color, stones, count, placement "
    "\n\nThe output must be photorealistic — the clothing should look naturally worn "
    "with proper fit, draping, and shadows matching the person's body."
)


# ---------------------------------------------------------------------------
# Nano Banana Module — Generates image with clothing transfer
# ---------------------------------------------------------------------------

import time as _time

GENERATION_MODELS = [
    "gemini-2.5-flash-image",
]

def _call_generation_model(source_part, target_part, prompt: str):
    """Call the generation model with target + source reference images."""
    for model_name in GENERATION_MODELS:
        for attempt in range(3):
            try:
                print(f"[GEN] Trying {model_name} (attempt {attempt+1}/3)...")
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[
                        target_part,
                        (
                            "👆 THIS IS THE PERSON. This is who you are editing. "
                            "Keep their face, skin, hair, body, pose, and background EXACTLY as they are. "
                            "You will ONLY change their clothing and jewelry."
                        ),
                        source_part,
                        (
                            "👆 THIS IS THE CLOTHING REFERENCE. "
                            "IGNORE the person in this photo — only look at the DRESS and JEWELRY. "
                            "Copy this EXACT outfit onto the person from the first photo.\n\n"
                            "⚠️ IMPORTANT: Output must show ONLY ONE PERSON (from the first photo). "
                            "Do NOT merge, blend, or overlay the two photos together.\n\n"
                            + prompt
                        ),
                    ],
                    config=types.GenerateContentConfig(
                        response_modalities=["Text", "Image"],
                        system_instruction=GENERATION_SYSTEM_INSTRUCTION,
                    ),
                )
                print(f"[GEN] Success with {model_name}!")
                return resp
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    wait = 10 * (attempt + 1)
                    print(f"[GEN] 503 overloaded — waiting {wait}s before retry...")
                    _time.sleep(wait)
                else:
                    print(f"[GEN] Non-retryable error on {model_name}: {e}")
                    break  # try next model
        print(f"[GEN] All attempts failed for {model_name}, trying next model...")
    
    raise Exception("All generation models failed. Please try again later.")


def _extract_response_parts(response) -> tuple[str | None, bytes | None]:
    """Extract text and image from model response."""
    text_result = None
    image_result = None
    try:
        # Try candidates first (some models use this structure)
        parts = None
        if hasattr(response, 'candidates') and response.candidates:
            parts = response.candidates[0].content.parts
        elif hasattr(response, 'parts') and response.parts:
            parts = response.parts
        
        if parts:
            for part in parts:
                if hasattr(part, 'text') and part.text is not None:
                    text_result = part.text
                elif hasattr(part, 'inline_data') and part.inline_data is not None:
                    image_result = part.inline_data.data
    except Exception as e:
        print(f"[ERROR] Failed to extract response parts: {e}")
        traceback.print_exc()
    return text_result, image_result


def generate_image(source_image_bytes: bytes, source_mime: str,
                   target_image_bytes: bytes, target_mime: str,
                   details: dict, user_instructions: str = "") -> tuple[str | None, bytes | None]:
    """
    Virtual try-on: dress the target person using SOURCE image + JSON details.
    
    Strategy:
      1. Build a detailed prompt from extracted clothing details (JSON)
      2. Send SOURCE image (dress reference) + TARGET image + text prompt
      3. If no image returned, retry once with a simplified prompt
    
    Returns (text_response, image_bytes) tuple.
    """
    prompt = build_generation_prompt(details, user_instructions)

    # Log the prompt for debugging
    print("=" * 60)
    print("GENERATION PROMPT SENT TO MODEL:")
    print("=" * 60)
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    print("=" * 60)

    source_part = types.Part.from_bytes(data=source_image_bytes, mime_type=source_mime)
    target_part = types.Part.from_bytes(data=target_image_bytes, mime_type=target_mime)

    # Attempt 1: Full prompt with both images
    try:
        response = _call_generation_model(source_part, target_part, prompt)
        text_result, image_result = _extract_response_parts(response)
    except Exception as e:
        print(f"[ERROR] Generation attempt 1 failed: {e}")
        traceback.print_exc()
        text_result, image_result = None, None

    # Attempt 2: Retry with simplified prompt if no image was returned
    if image_result is None:
        print("[RETRY] No image in first attempt. Retrying with simplified prompt...")
        simple_prompt = (
            f"Copy the EXACT outfit and jewelry from IMAGE 1 onto the person in IMAGE 2. "
            f"The outfit is: {details.get('dress_type', 'clothing')}. "
            f"Primary color: {details.get('primary_color', 'not specified')}. "
            f"Keep the person's face, body, hair, skin, and background EXACTLY the same. "
            f"Only change their clothes and jewelry to match IMAGE 1."
        )
        try:
            response = _call_generation_model(source_part, target_part, simple_prompt)
            text_result, image_result = _extract_response_parts(response)
        except Exception as e:
            print(f"[ERROR] Generation attempt 2 failed: {e}")
            traceback.print_exc()

    return text_result, image_result


# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Analyze a source image and return structured clothing details."""
    if client is None:
        return jsonify({"error": "GEMINI_API_KEY not configured on server"}), 503
    try:
        if "image" not in request.files:
            return jsonify({"error": "No image file provided"}), 400

        file = request.files["image"]
        image_bytes = file.read()
        mime_type = file.content_type or "image/jpeg"

        details = analyze_image(image_bytes, mime_type)
        return jsonify({"success": True, "details": details})

    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse vision model output as JSON"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompt-preview", methods=["POST"])
def api_prompt_preview():
    """Debug: Return the exact generation prompt that would be sent to the model."""
    try:
        details_str = request.form.get("details") or request.get_json(silent=True, force=True)
        if isinstance(details_str, str):
            details = json.loads(details_str)
        elif isinstance(details_str, dict):
            details = details_str
        else:
            return jsonify({"error": "No details provided"}), 400

        prompt = build_generation_prompt(details)
        return jsonify({"success": True, "prompt": prompt})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate clothing transfer: source dress image + target person."""
    if client is None:
        return jsonify({"error": "GEMINI_API_KEY not configured on server"}), 503
    try:
        if "target_image" not in request.files:
            return jsonify({"error": "No target image provided"}), 400
        if "source_image" not in request.files:
            return jsonify({"error": "No source image provided"}), 400

        details_str = request.form.get("details")
        if not details_str:
            return jsonify({"error": "No details JSON provided"}), 400

        details = json.loads(details_str)
        user_instructions = request.form.get("user_instructions", "")

        source_file = request.files["source_image"]
        source_bytes = source_file.read()
        source_mime = source_file.content_type or "image/jpeg"

        target_file = request.files["target_image"]
        target_bytes = target_file.read()
        target_mime = target_file.content_type or "image/jpeg"

        # Build prompt for response (so UI can show it)
        prompt_text = build_generation_prompt(details, user_instructions)

        text_resp, image_bytes = generate_image(
            source_bytes, source_mime,
            target_bytes, target_mime,
            details, user_instructions,
        )

        if image_bytes is None:
            return jsonify({
                "error": "Model did not return an image. " + (text_resp or ""),
                "prompt": prompt_text,
            }), 500

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        return jsonify({
            "success": True,
            "image": image_b64,
            "text": text_resp,
            "prompt": prompt_text,
        })

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid details JSON"}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
