import gradio as gr
import csv
import re
import sys
import io
import os
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

# Install nltk data if not present
try:
    import nltk
    nltk.download('punkt', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)
    nltk.download('universal_tagset', quiet=True)
except:
    pass

# Try to import urbans, install if not available
try:
    from urbans.translator import Translator
    from urbans.misc import load_grammar, load_dictionary
    from urbans.tree_manipulation import apply_transformations, tree_to_string
except ImportError:
    print("Installing urbans package from GitHub...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "git+https://github.com/pyurbans/urbans.git"])
    from urbans.translator import Translator
    from urbans.misc import load_grammar, load_dictionary
    from urbans.tree_manipulation import apply_transformations, tree_to_string

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
    except Exception as e:
        print(f"Error loading dictionary: {e}")
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

# ---------- Enhanced TwiTranslator Class ------------------------------------------------------
class TwiTranslator:
    def __init__(self, sentences, **kw):
        self.phrases = kw.pop("phrases", {})
        self.src_grammar_str = kw.pop("src_grammar")
        self.src_to_tgt_grammar = kw.pop("src_to_tgt_grammar", {})
        self.src_to_tgt_dictionary = kw.pop("src_to_tgt_dictionary", {})
        
        # Build extended grammar with proper nouns
        grammar_str = build_extended_grammar(self.src_grammar_str, sentences)
        
        # Initialize the urbans Translator
        self.translator = Translator(
            grammar=grammar_str,
            src_to_tgt_grammar=self.src_to_tgt_grammar,
            src_to_tgt_dictionary=self.src_to_tgt_dictionary
        )
        
        # Store sentences for reference
        self.sentences = sentences

    def translate(self, sentences):
        out = []
        for s in sentences:
            key = s.lower()
            
            # Check if it's a known phrase
            if key in self.phrases:
                out.append(self.phrases[key])
                continue
            
            try:
                # Use urbans translator
                raw = self.translator.translate([s])
                tw = raw[0] if raw else s
                
                # Post-processing
                tw = tw.replace("I ", "Me ").replace(" I", " Me")
                tw = tw.replace(" i ", " me ").replace(" i,", " me,")
                tw = tw.replace(" i.", " me.").replace(" i!", " me!")
                
                # Capitalize first letter
                if tw and len(tw) > 0:
                    tw = tw[0].upper() + tw[1:]
                
            except Exception as e:
                print(f"Translation error for '{s}': {e}")
                # Fallback to dictionary lookup
                tw = self.dictionary_fallback(s)
            
            out.append(tw)
        return out
    
    def dictionary_fallback(self, sentence):
        """Fallback translation using dictionary only."""
        words = sentence.split()
        translated_words = []
        
        for word in words:
            lower_word = word.lower()
            if lower_word in self.src_to_tgt_dictionary:
                trans = self.src_to_tgt_dictionary[lower_word]
                if trans:  # Only add if translation exists
                    translated_words.append(trans)
                else:
                    translated_words.append(word)
            elif lower_word in self.phrases:
                translated_words.append(self.phrases[lower_word])
            else:
                translated_words.append(word)
        
        result = " ".join(translated_words)
        # Apply pronoun fixes
        result = result.replace("I ", "Me ").replace(" I", " Me")
        return result

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
    translation = ""
    
    try:
        if show_details:
            f = io.StringIO()
            with redirect_stdout(f):
                print(f"=== TRANSLATION PROCESS FOR: '{english_sentence}' ===")
                print(f"\n1. Loading dictionary...")
                print(f"   - Words: {len(d)} entries")
                print(f"   - Phrases: {len(p)} entries")
                
                print(f"\n2. Creating translator with extended grammar...")
                # Create translator
                t = TwiTranslator(
                    sentences=[english_sentence],
                    src_grammar=ENG_GRAMMAR,
                    src_to_tgt_grammar=ENG_TO_TWI_GRAMMAR,
                    src_to_tgt_dictionary=d,
                    phrases=p
                )
                
                print(f"\n3. Translating sentence...")
                # Translate
                result = t.translate([english_sentence])[0]
                
                print(f"\n4. Results:")
                print(f"   Input: '{english_sentence}'")
                print(f"   Output: '{result}'")
                
                # Show grammar info
                print(f"\n5. Grammar Information:")
                print(f"   - Source grammar rules: {len(ENG_GRAMMAR.split('\\n'))}")
                print(f"   - Transformation rules: {len(ENG_TO_TWI_GRAMMAR)}")
                
                # Show dictionary entries used
                print(f"\n6. Dictionary Lookups:")
                words_used = []
                for word in english_sentence.lower().split():
                    clean_word = word.strip('.,!?;:')
                    if clean_word in d:
                        words_used.append(f"'{clean_word}' -> '{d[clean_word]}'")
                    elif clean_word in p:
                        words_used.append(f"'{clean_word}' -> '{p[clean_word]}' (phrase)")
                
                if words_used:
                    for entry in words_used:
                        print(f"   - {entry}")
                else:
                    print(f"   No direct dictionary matches found")
                
                print("\n" + "="*50)
                
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
            
    except Exception as e:
        error_msg = f"Error during translation: {str(e)}"
        print(error_msg)
        translation = f"Translation error: {str(e)}"
        if show_details:
            debug_output += f"\n{error_msg}"
    
    # Handle unsupported sentences
    if (translation.lower() == english_sentence.lower() and 
        english_sentence.lower() not in p and
        not translation.startswith("Translation error")):
        translation = f"Note: The sentence doesn't fully match the grammar rules. Some words might not be translated."
    
    return translation, debug_output

# ---------- Gradio Interface ----------------------------------------------------
def create_interface():
    """Create and return the Gradio interface."""
    
    # Custom CSS for better styling
    custom_css = """
    .gradio-container {
        max-width: 900px !important;
        margin: auto;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .title {
        text-align: center;
        font-size: 2.2em !important;
        font-weight: 800 !important;
        margin-bottom: 15px !important;
        color: #2c3e50;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
    }
    .subtitle {
        text-align: center;
        font-size: 1.2em !important;
        color: #5d6d7e;
        margin-bottom: 30px !important;
        font-weight: 400;
    }
    .input-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 25px;
        border-radius: 15px;
        margin-bottom: 20px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
    }
    .output-box {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 25px;
        border-radius: 15px;
        margin-bottom: 20px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        color: white;
        font-size: 1.2em;
        font-weight: 500;
    }
    .debug-box {
        background-color: #2c3e50;
        color: #ecf0f1;
        border-radius: 10px;
        padding: 20px;
        border-left: 5px solid #3498db;
        font-family: 'Courier New', monospace;
        font-size: 0.95em;
        white-space: pre-wrap;
        line-height: 1.5;
        margin-top: 20px;
    }
    .example-box {
        background: #f8f9fa;
        border: 2px dashed #dee2e6;
        border-radius: 10px;
        padding: 12px;
        margin: 8px 0;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    .example-box:hover {
        background: #e9ecef;
        border-color: #3498db;
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    .button-primary {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
        border: none;
        padding: 12px 30px;
        font-size: 1.1em;
        font-weight: 600;
        border-radius: 50px;
        transition: all 0.3s ease;
    }
    .button-primary:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
    }
    .button-secondary {
        background: #95a5a6;
        color: white !important;
        border: none;
        padding: 12px 30px;
        font-size: 1.1em;
        border-radius: 50px;
        transition: all 0.3s ease;
    }
    .button-secondary:hover {
        background: #7f8c8d;
        transform: translateY(-2px);
    }
    .checkbox-container {
        background: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        margin: 15px 0;
    }
    .info-box {
        background: #e8f4fc;
        border-left: 4px solid #3498db;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    """
    
    # Define the interface
    with gr.Blocks(css=custom_css, theme=gr.themes.Soft(primary_hue="purple", secondary_hue="pink")) as interface:
        # Title Section
        gr.Markdown(
            """
            <div style="text-align: center; padding: 20px 0;">
                <h1 style="margin: 0; color: #2c3e50;">🇬🇭 English to Twi Translator</h1>
                <p style="color: #7f8c8d; font-size: 1.1em; margin-top: 10px;">
                    Powered by urbans grammar-based translation framework
                </p>
            </div>
            """,
            elem_classes="title-section"
        )
        
        with gr.Row():
            with gr.Column(scale=2):
                # Input Section
                with gr.Group():
                    gr.Markdown("### 📝 Enter English Sentence")
                    english_input = gr.Textbox(
                        label="",
                        placeholder="Type your English sentence here... (e.g., 'I love good dogs')",
                        lines=3,
                        max_lines=3,
                        elem_id="english-input"
                    )
                    
                    # Input validation info
                    gr.Markdown(
                        """
                        <div class="info-box">
                        ⚠️ <strong>Note:</strong> Enter only one complete sentence at a time.
                        The system uses grammar rules to parse and translate your sentence.
                        </div>
                        """,
                        elem_classes="info-box"
                    )
            
            with gr.Column(scale=2):
                # Output Section
                with gr.Group():
                    gr.Markdown("### 🎯 Twi Translation")
                    twi_output = gr.Textbox(
                        label="",
                        lines=3,
                        interactive=False,
                        elem_id="twi-output",
                        show_copy_button=True
                    )
        
        # Options Section
        with gr.Row():
            with gr.Column():
                with gr.Group():
                    gr.Markdown("### ⚙️ Translation Options")
                    with gr.Row():
                        show_details = gr.Checkbox(
                            label="Show detailed translation process",
                            value=False,
                            info="See grammar parsing, dictionary lookups, and debug information"
                        )
                    
                    with gr.Row():
                        translate_btn = gr.Button(
                            "🚀 Translate to Twi", 
                            variant="primary",
                            size="lg",
                            elem_classes="button-primary"
                        )
                        clear_btn = gr.Button(
                            "🗑️ Clear All", 
                            variant="secondary", 
                            size="lg",
                            elem_classes="button-secondary"
                        )
        
        # Debug Output Section
        debug_output = gr.Textbox(
            label="🔍 Translation Details",
            lines=15,
            interactive=False,
            visible=False,
            elem_id="debug-output",
            show_copy_button=True
        )
        
        # Examples Section
        with gr.Group():
            gr.Markdown("### 💡 Try These Examples")
            examples = gr.Examples(
                examples=[
                    ["I love good dogs"],
                    ["how are you"],
                    ["what is your name"],
                    ["I am going to the market"],
                    ["Kofi ne Kwame are going to Accra"],
                    ["I work at Google"],
                    ["Mary loves Kumasi"],
                    ["I met John at the bank"],
                    ["Barack Obama visited Ghana"],
                    ["I hate bad dogs"]
                ],
                inputs=[english_input],
                label="Click any example to try it:",
                examples_per_page=5
            )
        
        # Information Accordion
        with gr.Accordion("📚 About This Translator", open=False):
            gr.Markdown("""
            ### How It Works
            
            This translator uses a **grammar-based approach** powered by the [urbans](https://github.com/pyurbans/urbans) framework:
            
            1. **Parsing**: The English sentence is parsed using context-free grammar rules
            2. **Transformation**: Grammar rules are transformed from English to Twi syntax
            3. **Dictionary Lookup**: Words are translated using the dictionary
            4. **Post-processing**: Final adjustments for pronouns and capitalization
            
            ### Grammar Features
            
            - **Sentence Types**: Statements, questions, phrases
            - **Parts of Speech**: Nouns, verbs, adjectives, prepositions, pronouns
            - **Proper Nouns**: Names, places, organizations
            - **Multi-word Names**: Support for names like "Barack Obama"
            
            ### Limitations
            
            - Vocabulary limited to dictionary entries
            - Complex sentences may not translate perfectly
            - Some English constructions may not be supported
            - Only one sentence at a time
            
            ### Built With
            
            - [urbans](https://github.com/pyurbans/urbans): Grammar-based translation framework
            - [Gradio](https://gradio.app/): Web interface
            - [NLTK](https://www.nltk.org/): Natural language processing
            """)
        
        # Statistics Section
        with gr.Row():
            with gr.Column():
                gr.Markdown("### 📊 Dictionary Statistics")
                gr.Markdown(f"""
                <div style="background: #f8f9fa; padding: 15px; border-radius: 10px;">
                    <p><strong>Words in dictionary:</strong> Loading...</p>
                    <p><strong>Grammar rules:</strong> {len(ENG_GRAMMAR.split('\\n'))} rules</p>
                    <p><strong>Transformation rules:</strong> {len(ENG_TO_TWI_GRAMMAR)} rules</p>
                </div>
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
        
        def clear_all():
            """Clear all inputs and outputs."""
            return ["", "", ""]
        
        def update_dictionary_stats():
            """Update dictionary statistics."""
            try:
                d, p = load_dict(CSV_FILE)
                total_words = len(d) + len(p)
                return f"""
                <div style="background: #f8f9fa; padding: 15px; border-radius: 10px;">
                    <p><strong>Words in dictionary:</strong> {total_words} entries ({len(d)} words, {len(p)} phrases)</p>
                    <p><strong>Grammar rules:</strong> {len(ENG_GRAMMAR.split('\\n'))} rules</p>
                    <p><strong>Transformation rules:</strong> {len(ENG_TO_TWI_GRAMMAR)} rules</p>
                </div>
                """
            except:
                return "Unable to load dictionary stats"
        
        # Connect components
        translate_btn.click(
            fn=translate_and_show,
            inputs=[english_input, show_details],
            outputs=[twi_output, debug_output]
        ).then(
            fn=update_dictionary_stats,
            inputs=[],
            outputs=[]
        )
        
        show_details.change(
            fn=toggle_debug,
            inputs=[show_details],
            outputs=[debug_output]
        )
        
        clear_btn.click(
            fn=clear_all,
            inputs=[],
            outputs=[english_input, twi_output, debug_output]
        )
        
        # Auto-clear debug when unchecked
        show_details.change(
            fn=lambda show_debug: "" if not show_debug else gr.update(),
            inputs=[show_details],
            outputs=[debug_output]
        )
        
        # Auto-translate when example is clicked (with a small delay for UX)
        english_input.submit(
            fn=translate_and_show,
            inputs=[english_input, show_details],
            outputs=[twi_output, debug_output]
        )
        
        # Load dictionary stats on startup
        interface.load(
            fn=update_dictionary_stats,
            inputs=[],
            outputs=[]
        )
    
    return interface

# ---------- Main Execution ----------------------------------------------------
if __name__ == "__main__":
    # Create and launch the interface
    interface = create_interface()
    
    # Configuration for Hugging Face Spaces
    share = os.getenv('SPACE_ID') is not None  # Auto-share if on Hugging Face
    
    interface.launch(
        server_name="0.0.0.0",
        share=share,
        debug=False,
        server_port=7860,
        show_error=True,
        favicon_path=None
    )
