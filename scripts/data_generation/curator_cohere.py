import os
import json
import threading
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv
import logging
import random

# Import Curator
from bespokelabs import curator

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
load_dotenv()
api_key = os.getenv("COHERE_API_KEY")
if api_key is None:
    raise ValueError("COHERE_API_KEY environment variable not set")

# --- Configuration ---
# Choose your desired model
model_config = {
    "name": "command-a-03-2025",
    "backend_params": {
        "api_key": api_key,
        "max_requests_per_minute": 5,
        "max_tokens_per_minute": 250_000
    }
}

# Define paths
PROMPT_DIR = "prompts"
DATASET_DIR = "data/jsonls"
DATASET_PATH = os.path.join(DATASET_DIR, "zraw.jsonl")
PROMPT_FILE_PATH = os.path.join(PROMPT_DIR, "altered_riddles_prompt.txt")
RIDDLES_FILE_PATH = os.path.join(PROMPT_DIR, "riddles.txt")

# Ensure directories exist
os.makedirs(DATASET_DIR, exist_ok=True)
os.makedirs(PROMPT_DIR, exist_ok=True)

# --- Pydantic Model for Structured Output ---
# Updated Pydantic model for the riddle structure
class AlteredRiddleEntry(BaseModel):
    original_riddle: str = Field(description="The original riddle.")
    original_answer: str = Field(description="The answer to the original riddle.")
    original_reasoning: str = Field(description="The reasoning explaining the original answer.")
    altered_riddle: str = Field(description="The slightly modified version of the original riddle.")
    altered_answer: str = Field(description="The different answer to the altered riddle.")
    altered_reasoning: str = Field(description="The reasoning explaining the altered answer.")

# --- Thread Lock for File Writing ---
file_lock = threading.Lock()

# --- Helper Functions ---
def load_prompt(prompt_path: str) -> Optional[str]:
    """Loads the prompt template from a file."""
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Prompt file not found at {prompt_path}")
        return None
    except Exception as e:
        logger.error(f"Error reading prompt file {prompt_path}: {e}")
        return None

def load_riddles(riddles_path: str) -> Optional[List[str]]:
    """Loads a list of riddles from a file."""
    try:
        with open(riddles_path, "r", encoding="utf-8") as f:
            # Each line represents a riddle
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        logger.error(f"Riddles file not found at {riddles_path}")
        return None
    except Exception as e:
        logger.error(f"Error reading riddles file {riddles_path}: {e}")
        return None

def save_result(dataset_path: str, result: Dict):
    """Append a single result dictionary to the dataset JSONL file (thread-safe)."""
    try:
        with file_lock:
            with open(dataset_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")
                f.flush()  # Force write to disk
        # logger.info(f"Successfully saved riddle result.") # Simplified log
    except Exception as e:
        logger.error(f"Error saving result to {dataset_path}: {e}\nResult: {result}")

# --- Curator LLM Class ---
# Renamed class to reflect riddle generation
class AlteredRiddleGenerator(curator.LLM):
    """
    Generates altered riddle dataset entries using an LLM via Curator.
    """
    def __init__(self, prompt_template: str, riddles: List[str], dataset_path: str, **kwargs): # Removed idioms parameter
        super().__init__(**kwargs)
        if not prompt_template:
             raise ValueError("Prompt template cannot be empty.")
        self.prompt_template = prompt_template
        self.riddles = riddles
        self.dataset_path = dataset_path
        logger.info(f"Initialized {self.__class__.__name__} to save to: {self.dataset_path}")
        logger.info(f"Using model: {kwargs.get('model_name', 'N/A')}")

    def prompt(self, input_data: Any) -> str:
        """
        Returns the static prompt template.
        Input_data is ignored here as the prompt is self-contained and generates
        a new example based on the instructions within the template itself.
        """
        return self.prompt_template.replace("{riddle_1}", random.choice(self.riddles)).replace("{riddle_2}", random.choice(self.riddles))

    def parse(self, input_data: Any, response: AlteredRiddleEntry) -> List[Dict]: # Updated response type hint
        """
        Parses the validated Pydantic response, saves it, and returns it.
        Curator handles the Pydantic validation based on `response_format`.
        """
        try:
            # Convert the Pydantic model instance to a dictionary
            result_dict = response.model_dump() # Use model_dump() for Pydantic v2+
            result_dict["model"] = model_config["name"] # Add model name used

            # Save the result
            save_result(self.dataset_path, result_dict)

            # Return the result dictionary within a list, as expected by Curator
            return [result_dict]

        except ValidationError as e:
            logger.error(f"Pydantic validation failed for LLM response: {e}")
            # Decide how to handle validation errors, e.g., log and continue or exit
            # exit() # Optional: Stop execution on validation error
            return [] # Return empty list to indicate failure for this item
        except Exception as e:
            logger.error(f"Error during parsing or saving: {e}", exc_info=True)
            # exit() # Optional: Stop execution on other parsing/saving errors
            return [] # Return empty list

# --- Main Execution Logic ---
def generate_dataset(num_entries: int):
    """Generates the dataset with the specified number of entries."""
    logger.info("--- Starting Altered Riddle Dataset Generation ---")

    # Load the prompt
    prompt_template = load_prompt(PROMPT_FILE_PATH)
    if not prompt_template:
        logger.error("Failed to load prompt template. Exiting.")
        return

    # Load the riddles
    riddles = load_riddles(RIDDLES_FILE_PATH)
    if not riddles:
        logger.error("Failed to load riddles. Exiting.")
        return

    # Ensure the output file exists (or create it)
    # Use the updated dataset path
    if not os.path.exists(DATASET_PATH):
        try:
            with open(DATASET_PATH, "w", encoding="utf-8") as _:
                 pass # Create empty file
            logger.info(f"Created empty dataset file: {DATASET_PATH}")
        except Exception as e:
            logger.error(f"Failed to create dataset file {DATASET_PATH}: {e}")
            return


    # Initialize the generator
    try:
        # Use the updated class name and parameters
        generator = AlteredRiddleGenerator(
            prompt_template=prompt_template,
            riddles=riddles,
            dataset_path=DATASET_PATH,
            model_name=model_config["name"],
            backend="litellm",
            backend_params=model_config["backend_params"],
            response_format=AlteredRiddleEntry,
            batch=False,
        )
    except Exception as e:
        logger.error(f"Failed to initialize AlteredRiddleGenerator: {e}")
        return

    # Prepare dummy input data for Curator (it needs an iterable, content doesn't matter here)
    input_list = [{} for _ in range(num_entries)]
    logger.info(f"Attempting to generate {num_entries} riddle entries...")

    # Run the generator - with a single call to Curator
    try:
        # The results are saved *during* the parse method calls within the generator
        generated_results = generator(input_list) # Curator iterates and calls prompt/parse

        successful_generations = len(generated_results) # Count successes based on non-empty returns from parse
        logger.info("--- Finished Generation Attempt ---")
        logger.info(f"Successfully generated and saved {successful_generations} entries.")
        if successful_generations < num_entries:
            logger.warning(f"Requested {num_entries} entries, but only {successful_generations} were successfully generated, parsed, and saved. Check logs for errors (e.g., validation, API issues).")
        logger.info(f"Dataset saved to: {DATASET_PATH}")

    except Exception as e:
        logger.error(f"An error occurred during the main generation loop: {e}", exc_info=True)

# --- Script Entry Point ---
if __name__ == "__main__":
    # Set the desired number of riddle pairs to generate
    NUM_ENTRIES_TO_GENERATE = 20 # Adjust as needed

    generate_dataset(NUM_ENTRIES_TO_GENERATE)
