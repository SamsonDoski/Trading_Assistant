# aws/lambda_handler.py
"""
AWS Lambda entry point for the trading pipeline.

Pure execution manager (per SRS V3.1 §2.1): it ensures the project is
importable and delegates ALL orchestration to run_live_pipeline(). It contains
zero strategy, sizing, or API-routing logic of its own — which is why it has
needed no changes across V3.1 -> V5.0.
"""
import os
import sys

# Make the project root importable whether Lambda invokes this as
# "aws.lambda_handler" or the file is run directly for local testing.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from live_controller import run_live_pipeline


def lambda_handler(event, context):
    """Triggered by AWS EventBridge at market open / close."""
    print("⚙️ AWS Lambda trigger received. Starting pipeline...")
    try:
        run_live_pipeline()
        return {"statusCode": 200, "body": "Pipeline execution complete."}
    except Exception as e:
        # Log to CloudWatch and return non-200 so monitoring can flag the run.
        print(f"❌ Fatal pipeline error: {e}")
        return {"statusCode": 500, "body": f"Pipeline failed: {e}"}


if __name__ == "__main__":
    # Local smoke test: python aws/lambda_handler.py
    lambda_handler({}, None)