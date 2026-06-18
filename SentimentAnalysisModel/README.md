# Optional Sentiment Model Weights

Argus can use a local Weibo multilingual sentiment model when the required Python ML dependencies and model files are available.

Model weights are not bundled in this public repository because they are large runtime artifacts. Public users can either allow the sentiment analyzer to download a compatible model through their configured Python environment, or provide their own local model files under the path expected by `InsightEngine/tools/sentiment_analyzer.py`.

The system is designed to degrade gracefully when the optional sentiment runtime is unavailable.
