import gradio as gr
import csv
import re
import sys
import io
from contextlib import redirect_stdout
from pathlib import Path

# Add current directory to path for custom modules
sys.path.append(str(Path(__file__).parent))

# Import from local urbans module
from urbans import Translator

CSV_FILE = "dict.csv"

ENG_GRAMMAR = """
S   -> NP VP | QP | PHRASE
NP  -> PRP | DET JJ NN | DET NN | JJ NN | NN | PROPN
VP  -> V NP | V PP | V NP PP | V | AUX V PP | AUX V
PP  -> P DET NN | P NN | P PROPN
QP  -> WP AUX PRP | WP V PRP NN
PHRASE -> WP AUX PRP
PRP -> 'I' | 'you' | 'me'
WP  -> 'how' | 'what' | 'where'
V   -> 'love' | 'hate' | 'going' | 'go' | 'is' | 'are' | 'loves' | 'met' | 'work' | 'visited'
AUX -> 'am' | 'is' | 'are' | 'do'
DET -> 'the' | 'a' | 'at'
P   -> 'to' | 'in' | 'on' | 'at'
JJ  -> 'good' | 'bad' | 'my' | 'your'
NN  -> 'dogs' | 'name' | 'market' | 'dog' | 'bank'
PROPN -> ANY_WORD
"""

ENG_TO_TWI_GRAMMAR = {
    "NP -> JJ NN": "NP -> NN JJ",
    "NP -> DET JJ NN": "NP -> NN JJ",
    "DET -> 'the'": "DET -> ''",
    "DET -> 'a'": "DET -> ''",
    "DET -> 'at'": "DET -> ''",
    "QP -> WP AUX PRP": "QP -> PRP WP",
    "QP -> WP V PRP NN": "QP -> PRP NN V WP",
    "VP -> AUX V PP": "VP -> V PP",
    "VP -> AUX V": "VP -> V",
    "AUX -> 'am'": "AUX -> ''",
    "AUX -> 'is'": "AUX -> ''",
    "AUX -> 'are'": "AUX -> ''",
}

# ---------- Helper Functions ---------------------------------------------------------
def load_dict(csv_file):
    """Load dictionary and phrases from CSV file."""
    d, p = {}, {}
    try:
        with open(csv_file, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                e = r["english"].strip()
                t = r["twi"].strip()
                typ = r.get("type", "word").lower()
                (p if typ == "phrase" else d)[e.lower()] = t
        return d, p
    except FileNotFoundError:
        print(f"Warning: {csv_file} not found. Using empty dictionary.")
        return {}, {}

_CAP_RE = re.compile(r"\b[A-Z][a-z]*(?:\s+(?:ne|and|of|de|bin|[A-Z][a-z]*))*\b")

def extract_multiword_names(sentences):
    """Extract multi-word names from sentences."""
    names = set()
    for s in sentences:
        for m in _CAP_RE.findall(s):
            tok = m.split()
            if len(tok) > 1:
                names.add(tuple(tok))
    return sorted(names)

def build_extended_grammar(base, sentences):
    """Return one grammar string with multi-word PROPN rules inserted."""
    single = {w for s in sentences for w in s.split()
              if w[0].isupper() and w not in {"I", "The", "A", "An"}}
    multi  = extract_multiword_names(sentences)

    lines = base.strip().split("\n")
    for i, l in enumerate(lines):
        if l.startswith("PROPN ->"):
            rest = [f"'{w}'" for w in sorted(single)]
            for j, mwp in enumerate(multi):
                rest.append(f"MWP_{j}")
            lines[i] = "PROPN -> " + " | ".join(rest)
            break

    # add MWP rules for every multi-word name
    for j, mwp in enumerate(multi):
        lines.append(f"MWP_{j} -> " + " ".join(f"'{w}'" for w in mwp))

    grammar = "\n".join(lines)
    return grammar

# ---------- Translator Class ------------------------------------------------------
class TwiTranslator(Translator):
    def __init__(self, sentences, **kw):
        self.phrases = kw.pop("phrases")
        grammar = build_extended_grammar(kw.pop("src_grammar"), sentences)

        # urbans.Translator wants the grammar as 1st positional argument
        super().__init__(grammar, **kw)

        # add multi-word names to dictionary so surface realiser finds them
        multi = extract_multiword_names(sentences)
        for mwp in multi:
            key = " ".join(mwp)
            if key.lower() not in self.src_to_tgt_dictionary:
                self.src_to_tgt_dictionary[key.lower()] = key

    def translate(self, sentences):
        out = []
        for s in sentences:
            key = s.lower()
            if key in self.phrases:
                out.append(self.phrases[key])
                continue
            try:
                raw = super().translate([s])
                tw = raw[0] or s
            except Exception as e:
                tw = s
            tw = tw.replace("I ", "Me ").replace(" I", " Me")
            out.append(tw)
        return out

# ---------- Translation Function for Gradio ------------------------------------
def translate_sentence(english_sentence, show_details=False):
    """
    Translate a single English sentence to Twi.
    
    Args:
        english_sentence: Input English sentence
        show_details: Whether to show debugging information
    
    Returns:
        Translated sentence and debug info
    """
    # Input validation
    if not english_sentence.strip():
        return "Please enter a sentence.", ""
    
    # Count sentences by checking for multiple periods or question marks
    sentences = [s.strip() for s in re.split(r'[.!?]+', english_sentence) if s.strip()]
    if len(sentences) > 1:
        return "Error: Please enter only one sentence at a time.", ""
    
    # Load dictionary
    d, p = load_dict(CSV_FILE)
    
    # Capture debug output if show_details is True
    debug_output = ""
    if show_details:
        f = io.StringIO()
        with redirect_stdout(f):
            # Create translator
            t = TwiTranslator(
                sentences=[english_sentence],
                src_grammar=ENG_GRAMMAR,
                src_to_tgt_grammar=ENG_TO_TWI_GRAMMAR,
                src_to_tgt_dictionary=d,
                phrases=p
            )
            
            # Translate
            result = t.translate([english_sentence])[0]
            
            # Print additional debug info
            print(f"\n=== TRANSLATION PROCESS ===")
            print(f"Input: {english_sentence}")
            print(f"Output: {result}")
            
            # Show dictionary entries used
            words_used = []
            for word in english_sentence.lower().split():
                if word in d:
                    words_used.append(f"{word} -> {d[word]}")
                elif word in p:
                    words_used.append(f"{word} -> {p[word]} (phrase)")
            
            if words_used:
                print(f"\nDictionary entries used:")
                for entry in words_used:
                    print(f"  {entry}")
            
        debug_output = f.getvalue()
        translation = result
    else:
        # Create translator without debug output
        t = TwiTranslator(
            sentences=[english_sentence],
            src_grammar=ENG_GRAMMAR,
            src_to_tgt_grammar=ENG_TO_TWI_GRAMMAR,
            src_to_tgt_dictionary=d,
            phrases=p
        )
        translation = t.translate([english_sentence])[0]
    
    # Handle unsupported sentences (if translation equals original)
    if translation.lower() == english_sentence.lower() and english_sentence.lower() not in p:
        translation = f"Note: '{english_sentence}' doesn't fully match the grammar rules. Some words might not be translated."
    
    return translation, debug_output

# ---------- Gradio Interface ----------------------------------------------------
def create_interface():
    """Create and return the Gradio interface."""
    
    # Custom CSS for better styling
    custom_css = """
    .gradio-container {
        max-width: 800px !important;
        margin: auto;
    }
    .title {
        text-align: center;
        font-size: 2em !important;
        font-weight: bold;
        margin-bottom: 20px !important;
        color: #2c3e50;
    }
    .subtitle {
        text-align: center;
        font-size: 1.1em !important;
        color: #7f8c8d;
        margin-bottom: 30px !important;
    }
    .output-box {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-left: 4px solid #3498db;
    }
    .debug-box {
        background-color: #f1f8e9;
        border-radius: 10px;
        padding: 15px;
        border-left: 4px solid #7cb342;
        font-family: monospace;
        font-size: 0.9em;
        white-space: pre-wrap;
    }
    """
    
    # Define the interface
    with gr.Blocks(css=custom_css, theme=gr.themes.Soft()) as interface:
        # Title
        gr.Markdown("# 🇬🇭 English to Twi Translator", elem_classes="title")
        gr.Markdown("Translate English sentences to Twi (Akan language spoken in Ghana)", 
                   elem_classes="subtitle")
        
        with gr.Row():
            with gr.Column(scale=2):
                # Input section
                english_input = gr.Textbox(
                    label="English Sentence",
                    placeholder="Enter an English sentence here...",
                    lines=3,
                    max_lines=3,
                    info="Enter only one sentence. Example: 'I love good dogs'"
                )
                
                # Options
                show_details = gr.Checkbox(
                    label="Show translation details",
                    value=False,
                    info="Check to see grammar parsing and dictionary lookups"
                )
                
                translate_btn = gr.Button("Translate to Twi", variant="primary", scale=1)
                clear_btn = gr.Button("Clear", variant="secondary", scale=0)
            
            with gr.Column(scale=2):
                # Output section
                twi_output = gr.Textbox(
                    label="Twi Translation",
                    lines=3,
                    interactive=False,
                    elem_classes="output-box"
                )
        
        # Debug output (initially hidden)
        debug_output = gr.Textbox(
            label="Translation Details",
            lines=10,
            interactive=False,
            visible=False,
            elem_classes="debug-box"
        )
        
        # Examples
        gr.Examples(
            examples=[
                ["I love good dogs"],
                ["how are you"],
                ["what is your name"],
                ["I am going to the market"],
                ["Kofi ne Kwame are going to Accra"],
                ["I work at Google"]
            ],
            inputs=[english_input],
            label="Try these examples:"
        )
        
        # Description
        gr.Markdown("""
        ### About this Translator
        This tool uses grammar-based translation rules and a dictionary to translate English to Twi.
        
        **Supported grammar patterns include:**
        - Simple sentences: "I love dogs"
        - Questions: "how are you", "what is your name"
        - Proper nouns: "Kofi", "Accra", "Google"
        - Prepositional phrases: "to the market", "at the bank"
        
        **Limitations:**
        - Currently supports a limited vocabulary (see dictionary)
        - Complex sentences might not translate perfectly
        - Only one sentence at a time
        """)
        
        # Event handlers
        def toggle_debug(show_debug):
            """Toggle visibility of debug output."""
            return gr.update(visible=show_debug)
        
        def translate_and_show(english, show_debug):
            """Translate and return results."""
            translation, debug = translate_sentence(english, show_debug)
            if show_debug:
                return translation, debug
            else:
                return translation, ""
        
        # Connect components
        translate_btn.click(
            fn=translate_and_show,
            inputs=[english_input, show_details],
            outputs=[twi_output, debug_output]
        )
        
        show_details.change(
            fn=toggle_debug,
            inputs=[show_details],
            outputs=[debug_output]
        )
        
        clear_btn.click(
            fn=lambda: ["", "", ""],
            inputs=[],
            outputs=[english_input, twi_output, debug_output]
        )
        
        # Auto-clear debug when unchecked
        show_details.change(
            fn=lambda show_debug: "" if not show_debug else gr.update(),
            inputs=[show_details],
            outputs=[debug_output]
        )
    
    return interface

# ---------- Main Execution ----------------------------------------------------
if __name__ == "__main__":
    # Create and launch the interface
    interface = create_interface()
    interface.launch(
        server_name="0.0.0.0",
        share=False,
        debug=False,
        server_port=7860
    )
