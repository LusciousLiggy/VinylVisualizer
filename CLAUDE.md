## Project Overview
This project connects to the Discogs API to pull my vinyl collection
and generate a visual, interactive HTML dashboard.

## Goals
- Fetch all records in my Discogs collection
- Display results in a modern, graphical HTML dashboard showing:
  - Total number of records
  - Estimated collection value
  - Breakdown by genre (pie or donut chart)
  - Breakdown by decade (bar chart)
  - Top 10 most valuable items (styled table or card layout)
  - Most recently added records (timeline or card feed)

## Design Requirements
- Output should be a single self-contained HTML file
- Use a clean, modern dark or light theme
- Use Chart.js for all graphs and visualizations
- Dashboard should be visually polished — cards, rounded corners,
  clear typography
- Should look good in a browser without any additional setup

## Key Info
- Language: Python
- Discogs username: jack.warren
- Output file: collection_dashboard.html

## Discogs API
- Base URL: https://api.discogs.com
- Auth method: personal access token
- Token should be stored in a .env file as DISCOGS_TOKEN

## Notes
- Do not hardcode API credentials in any script
- Always preview output before writing files
- Chart.js can be loaded via CDN — no need to install separately