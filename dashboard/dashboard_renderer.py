#!/usr/bin/env python3
"""
Dashboard Renderer - Renders index.html from template + JSON data
Usage: python dashboard_renderer.py [--template TEMPLATE] [--data DATA] [--output OUTPUT]

Generates /Users/tobyglennpeters/.openclaw/workspace/dashboard/index.html from:
- index.html.template (HTML with placeholders)
- dashboard.json (agent data and activities)
"""

import json
import argparse
from pathlib import Path

# Default paths relative to script location
SCRIPT_DIR = Path(__file__).parent
DEFAULT_TEMPLATE = SCRIPT_DIR / 'index.html.template'
DEFAULT_DATA = SCRIPT_DIR / 'dashboard.json'
DEFAULT_OUTPUT = SCRIPT_DIR / 'index.html'


def get_agent_card_placeholder(name: str) -> str:
    """Returns the HTML placeholder for an agent card by name."""
    upper_name = name.upper()
    return f"{{AGENT_CARD_{upper_name}}}"


def get_activity_item_placeholder(index: int) -> str:
    """Returns the HTML placeholder for an activity item by index."""
    return f"{{ACTIVITY_ITEM_{index}}}"


def normalize_emoji(emoji: str) -> str:
    """Handle multi-character emojis (like ⚙️☁️) for HTML display."""
    if len(emoji) > 2:
        return f'<span>{emoji}</span>'
    return emoji


def generate_agent_card(agent: dict) -> str:
    """Generate HTML card for an agent from JSON data."""
    name = agent['name']
    name_lower = name.lower()
    status = agent['status']
    is_active = status.lower() == 'active'
    emoji = normalize_emoji(agent['emoji'])
    
    # Handle Clawd's special icon wrapper
    icon_content = emoji
    if name == 'Clawd':
        icon_content = f'<span>{emoji}</span>'
    
    # Determine status class
    status_class = 'status-badge'
    card_classes = f"card {name_lower}"
    if is_active:
        card_classes += " active"
        status_display = status.capitalize()
    else:
        status_display = status.capitalize()
    
    html = f'''<div class="{card_classes}">
  <div class="card-header">
    <div class="icon{' clawd-icon' if name == 'Clawd' else ''}">{icon_content}</div>
    <div>
      <div style="font-weight:600">{name}</div>
      <div style="font-size:.75rem;color:#8b949e">{agent['role']}</div>
    </div>
    <span class="status-badge">{status_display}</span>
  </div>
  <div style="font-size:.875rem;color:#8b949e">{agent['description']}</div>
</div>'''
    return html


def generate_activity_item(activity: dict) -> str:
    """Generate HTML for an activity item."""
    activity_type = activity.get('type', 'default')
    html = f'''<div class="activity-item {activity_type}">
  <div class="activity-message">{activity['message']}</div>
  <div class="activity-time">{activity['time']}</div>
</div>'''
    return html


def render_dashboard(template_path: Path = DEFAULT_TEMPLATE,
                   data_path: Path = DEFAULT_DATA,
                   output_path: Path = DEFAULT_OUTPUT) -> None:
    """Render the dashboard HTML from template and data."""
    
    # Read JSON data
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Read template
    with open(template_path, 'r') as f:
        template = f.read()
    
    # Group agents by type (top agents vs subagents)
    all_agents = data['agents']
    top_agents = [a for a in all_agents if a['name'] in ['ARIA', 'Clawd', 'BOB']]
    subagents = [a for a in all_agents if a['name'] not in ['ARIA', 'Clawd', 'BOB']]
    
    # Replace agent cards in sidebar (desktop - top agents)
    top_agents_pattern = '{{TOP_AGENTS_DESKTOP}}'
    top_agents_html = '\n\n'.join(generate_agent_card(a) for a in top_agents)
    template = template.replace(top_agents_pattern, top_agents_html)
    
    # Replace agent cards in mobile view (top agents)
    top_agents_mobile_pattern = '{{TOP_AGENTS_MOBILE}}'
    top_agents_mobile_html = '\n'.join(generate_agent_card(a) for a in top_agents)
    template = template.replace(top_agents_mobile_pattern, top_agents_mobile_html)
    
    # Replace agent cards in main content (subagents)
    subagents_pattern = '{{SUBAGENTS_MAIN}}'
    subagents_html = '\n\n'.join(generate_agent_card(a) for a in subagents)
    template = template.replace(subagents_pattern, subagents_html)
    
    # Replace activity log
    activities_pattern = '{{ACTIVITY_LOG}}'
    activities_html = '\n'.join(generate_activity_item(a) for a in data['activities'])
    template = template.replace(activities_pattern, activities_html)
    
    # Write output
    with open(output_path, 'w') as f:
        f.write(template)
    
    print(f"Dashboard rendered successfully: {output_path}")
    print(f"  - Agents: {len(all_agents)} ({len(top_agents)} top, {len(subagents)} subagents)")
    print(f"  - Activities: {len(data['activities'])}")


def main():
    parser = argparse.ArgumentParser(description='Render dashboard HTML from template and JSON data')
    parser.add_argument('--template', type=Path, default=DEFAULT_TEMPLATE,
                        help=f'Template file (default: {DEFAULT_TEMPLATE})')
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA,
                        help=f'Data JSON file (default: {DEFAULT_DATA})')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT,
                        help=f'Output HTML file (default: {DEFAULT_OUTPUT})')
    
    args = parser.parse_args()
    render_dashboard(args.template, args.data, args.output)


if __name__ == '__main__':
    main()
