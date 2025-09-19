# 🚀 IngestRSS - 🗞️💵⚖️

![Header](wallpaper.png)

IngestRSS is an AWS-based RSS feed processing system that automatically fetches, processes, and stores articles from specified RSS feeds. This project is designed to support social scientists in progressing research on news and media.

## 🎯 Purpose

The primary goal of IngestRSS is to provide researchers with a robust, scalable solution for collecting and analyzing large volumes of news data. By automating the process of gathering articles from diverse sources, this tool enables social scientists to focus on their research questions and data analysis, rather than the complexities of data collection.

## 🚀 Getting Started

### Prerequisites

- Python 3.12
- AWS account with necessary permissions
- AWS CLI configured with your credentials

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/IngestRSS.git
   cd IngestRSS
   ```

2. Install required packages:
   ```
   python -m pip install -r requirements.txt
   ```

3. Set up your environment variables:
   - Find the file named `template.env` in your folder.
   - Make a copy of this file in the same folder.
   - Rename the copy to `.env` (make sure to include the dot at the start).
   - Open the `.env` file and fill in your information where you see `***`.
   
   Here's what you need to fill in:
   ```
   AWS_REGION=***
   AWS_ACCOUNT_ID=***
   AWS_ACCESS_KEY_ID=***
   AWS_SECRET_ACCESS_KEY=***
   ```
   
   The other settings in the file are already set up for you, but you can change them if you need to.

4. Launch the application:
   ```
   python launch.py
   ```

## 🛠️ Configuration

- **RSS feeds can be modified in the `rss_feeds.json` file.**
- CloudFormation templates are located in `src/infra/cloudformation/`.
- Lambda function code is in `src/lambda_function/src/`.

### S3 bucket naming convention

This project uses a single S3 base name configured via the `S3_BASE_NAME` environment variable. The launcher and `template.env` generate two buckets from this base:

- Content bucket: `${S3_BASE_NAME}-${AWS_REGION}`
- Zipped lambda artifacts bucket: `${S3_BASE_NAME}-zipped-${AWS_REGION}`

Using a `-zipped-` suffix for the zipped bucket prevents accidental collisions with the content bucket when deploying CloudFormation stacks.

If you regenerate `.env` using the launcher (`python src/launch/launch_env.py`) it will prompt for `S3_BASE_NAME` (default: `ai-researcher-rss`) and write both derived env vars into the saved `.env` file.

## 📊 Monitoring

The Lambda function logs its activities to CloudWatch Logs. You can monitor the function's performance and any errors through the AWS CloudWatch console.

## 🤝 Contributing

Contributions are welcome, feel free to see open issues to get started. 


## 📄 License

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

