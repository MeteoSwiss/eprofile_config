#!/usr/bin/env python3
"""
Script to update MWR l12l2 configuration from raw2l1 configuration.

This script:
1. Reads configuration files from the raw2l1 folder
2. Updates corresponding configuration files in the l12l2 folder
3. Logs changes and provides a summary of updates
"""

import os
import sys
import json
import yaml
import logging
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Union, Any, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('update_mwr_config')

class ConfigUpdater:
    """Class to handle MWR configuration updates from raw2l1 to l12l2."""
    
    def __init__(self, base_path: Path, raw2l1_dir: str = "raw2l1", l12l2_dir: str = "l12l2"):
        """
        Initialize the ConfigUpdater.
        
        Args:
            base_path: Base path where both directories are located
            raw2l1_dir: Name of the source configuration directory
            l12l2_dir: Name of the target configuration directory
        """
        self.base_path = Path(base_path)
        self.raw2l1_path = self.base_path / raw2l1_dir
        self.l12l2_path = self.base_path / l12l2_dir
        self.success_files = []
        self.skipped_files = []
        self.error_files = []
        
        # Verify directories exist
        if not self.raw2l1_path.exists():
            raise FileNotFoundError(f"Source directory not found: {self.raw2l1_path}")
        if not self.l12l2_path.exists():
            raise FileNotFoundError(f"Target directory not found: {self.l12l2_path}")

    def _load_config(self, file_path: Path) -> Dict:
        """
        Load configuration from a file.
        Supports JSON and YAML formats.
        
        Args:
            file_path: Path to the configuration file
            
        Returns:
            Dict containing configuration data
        """
        try:
            suffix = file_path.suffix.lower()
            with open(file_path, 'r') as f:
                if suffix in ['.json']:
                    return json.load(f)
                elif suffix in ['.yml', '.yaml']:
                    return yaml.safe_load(f)
                else:
                    # Try to determine format based on content
                    content = f.read()
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        try:
                            return yaml.safe_load(content)
                        except yaml.YAMLError:
                            # If all else fails, return the raw content
                            return {"raw_content": content}
        except Exception as e:
            logger.error(f"Error loading config from {file_path}: {str(e)}")
            raise

    def _check_config(self, source_config: Dict, target_config: Dict) -> Dict:
        """
        Compare target configuration with values from source configuration.
        
        Args:
            source_config: Configuration from raw2l1
            target_config: Configuration from l12l2
            
        Returns:
            Nothing
        """
        differences = {}

        # We only want to update the meta-data fields, not the entire config
        meta_data_keys = [
            "wigos_station_id", "instrument_id", "station_latitude", "station_longitude",
            "station_altitude", 
        ]
        for key in meta_data_keys:
            source_value = source_config.get(key)
            target_value = target_config.get(key)
            if source_value is not None and target_value is not None:
                if source_value != target_value:
                    print(f"Key '{key}': target='{target_value}' vs source='{source_value}'")
                    differences[key] = (target_value, source_value)
            else:
                print(f"Key '{key}' missing in source or target config")
                differences[key] = (target_value, source_value)

        return differences
    
    def compare_file(self, raw2l1_file: Path) -> bool:
        """
        Compare the information from an l12l2 configuration file from a raw2l1 configuration file.
        
        Args:
            raw2l1_file: Path to the raw2l1 configuration file

        Returns:
            True if comparison was successful (all infos match), False otherwise
        """
        # Compute corresponding path in l12l2
        relative_path = raw2l1_file.relative_to(self.raw2l1_path)
        # Replace the base filename as the config files may have different naming conventions
        # Example: config_MWR_XXX_ID.yaml in raw2l1 changes names to config_WIGOS_instrument_id.yaml in l12l2
        # First read wigos_station_id and instrument_id from raw2l1 file 
        logger.info("----------------------------------------")
        logger.info(f"Processing file: {raw2l1_file}")

        try:
            raw2l1_config = self._load_config(raw2l1_file)
            wigos_id = raw2l1_config.get("nc_attributes", {}).get("wigos_station_id", "")
            instrument_id = raw2l1_config.get("nc_attributes", {}).get("instrument_id", "")
            if not wigos_id:
                logger.warning(f"No wigos_station_id found in {raw2l1_file}, skipping file.")
                self.skipped_files.append(str(raw2l1_file))
                return True
            new_base_filename = f"config_{wigos_id}_{instrument_id}.yaml"
            logger.info(f"Mapping to target filename: {new_base_filename}")
            relative_path = relative_path.parent / new_base_filename
        except Exception as e:
            logger.error(f"Error processing {raw2l1_file}: {str(e)}")
            self.error_files.append(str(relative_path))
            return False
        
        l12l2_file = self.l12l2_path / relative_path
        
        try:
            # Check if target file exists
            if not l12l2_file.exists():
                logger.warning(f"Target file does not exist: {l12l2_file}, please create it first")
                self.skipped_files.append(str(raw2l1_file))
                return True
            
            # Load configurations
            raw2l1_config = self._load_config(raw2l1_file)
            l12l2_config = self._load_config(l12l2_file)
            # Check if configuration needs an update
            differences = self._check_config(raw2l1_config.get("nc_attributes", {}), l12l2_config)

            if len(differences) == 0:
                logger.info(f"No differences found for {l12l2_file}, nothing to update.")
                print(differences)
                self.success_files.append(str(relative_path))
                return True
            else:
                self.error_files.append(str(relative_path))
                logger.warning(f"Differences found for {l12l2_file}: {differences}")
                logger.warning("Please update the target configuration file manually to avoid overwriting custom settings.")
                return False
            
  
        except Exception as e:
            logger.error(f"Error updating {l12l2_file}: {str(e)}")
            self.error_files.append(str(relative_path))
            return False

    def update_all(self, file_pattern: str = "*.*") -> Dict[str, List[str]]:
        """
        Compare all matching configuration files from raw2l1 to l12l2 and list the differences.
        
        Args:
            file_pattern: Glob pattern to match configuration files
            
        Returns:
            Dictionary with lists of updated, skipped and error files
        """
        # Find all configuration files in raw2l1
        for file_path in self.raw2l1_path.glob(f"**/{file_pattern}"):
            if file_path.is_file():
                result = self.compare_file(file_path)
                if not result:
                    relative_path = file_path.relative_to(self.raw2l1_path)
                    self.skipped_files.append(str(relative_path))
        
        return {
            "updated": self.success_files,
            "skipped": self.skipped_files,
            "errors": self.error_files
        }

    def generate_summary(self, output_file: Optional[Path] = None) -> str:
        """
        Generate a summary of the update operation.
        
        Args:
            output_file: Optional file to write the summary to
            
        Returns:
            Summary text
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        summary = [
            f"MWR Configuration Update Summary",
            f"Date: {now}",
            f"",
            f"Source directory: {self.raw2l1_path}",
            f"Target directory: {self.l12l2_path}",
            f"",
            f"Files successful: {len(self.success_files)}",
            f"Files skipped: {len(self.skipped_files)}",
            f"Files with errors: {len(self.error_files)}",
            f"",
        ]
        
        if self.success_files:
            summary.append("Successful files:")
            for file in sorted(self.success_files):
                summary.append(f"  - {file}")
            summary.append("")
        
        if self.skipped_files:
            summary.append("Skipped files:")
            for file in sorted(self.skipped_files):
                summary.append(f"  - {file}")
            summary.append("")
        
        if self.error_files:
            summary.append("Files with errors:")
            for file in sorted(self.error_files):
                summary.append(f"  - {file}")
            summary.append("")
        
        summary_text = "\n".join(summary)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(summary_text)
        
        return summary_text


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Update MWR l12l2 config from raw2l1 config.')
    parser.add_argument('--base-path', type=str, default=os.getcwd(),
                        help='Base path where both raw2l1 and l12l2 directories are located')
    parser.add_argument('--raw2l1-dir', type=str, default='raw2l1',
                        help='Name of the source configuration directory')
    parser.add_argument('--l12l2-dir', type=str, default='l12l2',
                        help='Name of the target configuration directory')
    parser.add_argument('--pattern', type=str, default='*.yaml',
                        help='File pattern to match (e.g., "*.json", "*.yml")')
    parser.add_argument('--summary', type=str, default='update_summary.txt',
                        help='File to save the summary report')
    return parser.parse_args()


def main():
    """Main function."""
    args = parse_arguments()
    
    try:
        # Initialize the config updater
        updater = ConfigUpdater(
            base_path=args.base_path,
            raw2l1_dir=args.raw2l1_dir,
            l12l2_dir=args.l12l2_dir
        )
        
        # Perform the update
        logger.info(f"Starting configuration update from {args.raw2l1_dir} to {args.l12l2_dir}")
        results = updater.update_all(file_pattern=args.pattern)
        
        # Generate and print summary
        # summary = updater.generate_summary(output_file=args.summary)
        # print("\n" + summary)
        
        # logger.info(f"Configuration update completed. Summary saved to {args.summary}")
        
        # Return appropriate exit code
        if results['errors']:
            return 1
        return 0
        
    except Exception as e:
        logger.error(f"Error during configuration update: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())