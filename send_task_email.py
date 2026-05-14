import os
import requests
import pytz
from datetime import datetime, date, timedelta

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']
RESEND_API_KEY = os.environ['RESEND_API_KEY']
SEND_TYPE = os.environ.get('SEND_TYPE', '')  # 'morning' or 'followup'
TO_EMAIL = os.environ.get('TO_EMAIL', 'jacob@goodmancampaigns.com')

PAGES_URL = 'https://JacobGC22.github.io/goodman-tasks'

NAVY = '#1B3A8C'
NAVY_DARK = '#152D6E'
GOLD = '#F5A800'
BG = '#F4F6FB'
WHITE = '#FFFFFF'
MUTED = '#888888'
DANGER = '#C0392B'
BORDER = '#D6DCF0'
TEXT = '#1a1a1a'

# Group header colors — match the dashboard
COLOR_OVERDUE   = DANGER
COLOR_TODAY     = '#1D6E3A'
COLOR_TOMORROW  = '#2E5FA8'
COLOR_THIS_WEEK = '#3A5FAF'
COLOR_NEXT_WEEK = '#4A6FBF'
COLOR_LATER     = '#5B7ABF'
COLOR_NO_DATE   = '#6B7A9E'

MOUNTAIN = pytz.timezone('America/Denver')


def get_mountain_now():
    return datetime.now(MOUNTAIN)


def get_mountain_today():
    return get_mountain_now().strftime('%Y-%m-%d')


def get_mountain_dow():
    """0=Mon ... 6=Sun in Python's weekday(). Convert to 0=Sun ... 6=Sat."""
    py_dow = get_mountain_now().weekday()  # Mon=0 ... Sun=6
    # Convert: Sun=0, Mon=1, ..., Sat=6
    return (py_dow + 1) % 7


def is_weekend():
    now_mt = get_mountain_now()
    is_wknd = now_mt.weekday() >= 5  # 5=Sat, 6=Sun in Python
    print(f'STATUS: Day of week (Mountain): {now_mt.strftime("%A")} — weekend={is_wknd}')
    return is_wknd


def check_already_sent_today(send_type):
    key = f'last_sent_{send_type}'
    today = get_mountain_today()
    res = requests.get(
        f'{SUPABASE_URL}/rest/v1/settings?key=eq.{key}',
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
    )
    res.raise_for_status()
    rows = res.json()
    if rows and rows[0]['value'].get('date') == today:
        print(f'STATUS: Already sent {send_type} today ({today}), skipping')
        return True
    return False


def mark_sent_today(send_type):
    key = f'last_sent_{send_type}'
    today = get_mountain_today()
    res = requests.post(
        f'{SUPABASE_URL}/rest/v1/settings',
        headers={
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates'
        },
        json={'key': key, 'value': {'date': today}}
    )
    res.raise_for_status()
    print(f'STATUS: Marked {send_type} as sent for {today}')


def check_followup_skipped():
    today = get_mountain_today()
    res = requests.get(
        f'{SUPABASE_URL}/rest/v1/settings?key=eq.skip_followup_date',
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
    )
    res.raise_for_status()
    rows = res.json()
    if rows and rows[0]['value'].get('date') == today:
        print(f'STATUS: Followup skipped for today ({today})')
        return True
    print('STATUS: Followup not skipped, sending')
    return False


def unhide_due_tasks():
    today = get_mountain_today()
    today_date = date.fromisoformat(today)
    res = requests.get(
        f'{SUPABASE_URL}/rest/v1/tasks?status=eq.open&is_hidden=eq.true',
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
    )
    res.raise_for_status()
    hidden = res.json()
    unhidden_count = 0
    for task in hidden:
        if not task.get('due_date'):
            continue
        task_date = date.fromisoformat(task['due_date'])
        if (task_date.year, task_date.month) <= (today_date.year, today_date.month):
            patch = requests.patch(
                f'{SUPABASE_URL}/rest/v1/tasks?id=eq.{task["id"]}',
                headers={
                    'apikey': SUPABASE_KEY,
                    'Authorization': f'Bearer {SUPABASE_KEY}',
                    'Content-Type': 'application/json',
                    'Prefer': 'return=minimal'
                },
                json={'is_hidden': False}
            )
            patch.raise_for_status()
            unhidden_count += 1
    if unhidden_count:
        print(f'STATUS: Unhid {unhidden_count} recurring task(s)')


def fetch_tasks():
    res = requests.get(
        f'{SUPABASE_URL}/rest/v1/tasks',
        params={
            'status': 'eq.open',
            'is_hidden': 'eq.false',
            'order': 'due_date.asc.nullslast,created_at.asc'
        },
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
    )
    res.raise_for_status()
    return res.json()


def get_due_status(date_str):
    """
    Groups:
      overdue, today, tomorrow, this_week, next_week, later, no_date

    Week = Sunday through Saturday.
    Due This Week = days after tomorrow through this Saturday, only on Sun(0)-Thu(4).
    Due Next Week = following Sun-Sat, only shown on Wed(3)-Sat(6).
    """
    if not date_str:
        return 'no_date'

    today_str = get_mountain_today()
    today_date = date.fromisoformat(today_str)
    task_date = date.fromisoformat(date_str)
    dow = get_mountain_dow()  # 0=Sun, 1=Mon, ..., 6=Sat

    tomorrow_date = today_date + timedelta(days=1)
    tomorrow_str = tomorrow_date.isoformat()

    # This Saturday
    days_to_sat = (6 - dow) % 7
    saturday_date = today_date + timedelta(days=days_to_sat)
    saturday_str = saturday_date.isoformat()

    # Next week Sunday and Saturday
    next_sunday_date = saturday_date + timedelta(days=1)
    next_saturday_date = next_sunday_date + timedelta(days=6)

    if date_str < today_str:
        return 'overdue'
    if date_str == today_str:
        return 'today'
    if date_str == tomorrow_str:
        return 'tomorrow'

    # Due This Week: after tomorrow through Saturday, only Sun(0) through Thu(4)
    if dow <= 4:
        if task_date > tomorrow_date and task_date <= saturday_date:
            return 'this_week'

    # Due Next Week: only on Wed(3) through Sat(6)
    if dow >= 3:
        if next_sunday_date <= task_date <= next_saturday_date:
            return 'next_week'

    return 'later'


def format_date(date_str):
    if not date_str:
        return None
    d = date.fromisoformat(date_str)
    return d.strftime('%b %-d, %Y')


def section_header(title, color, count=None):
    count_html = ''
    if count is not None:
        count_html = f'<td align="right" style="padding:10px 16px;"><span style="font-size:12px;color:rgba(255,255,255,0.75);font-family:\'DM Sans\',Arial,sans-serif;">{count} task{"s" if count != 1 else ""}</span></td>'
    return f'''
      <tr>
        <td style="padding:0 0 10px 0;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:{color};border-radius:8px;">
            <tr>
              <td style="padding:10px 16px;">
                <span style="font-size:11px;font-weight:700;color:{WHITE};text-transform:uppercase;letter-spacing:1px;font-family:'DM Sans',Arial,sans-serif;">{title}</span>
              </td>
              {count_html}
            </tr>
          </table>
        </td>
      </tr>'''


def build_task_row(task):
    status = get_due_status(task.get('due_date'))
    complete_url = f"{PAGES_URL}/complete.html?id={task['id']}"
    snooze_url = f"{PAGES_URL}/snooze.html?id={task['id']}" if task.get('due_date') else None

    # Due label
    due_html = ''
    if task.get('due_date'):
        if status == 'overdue':
            due_html = f'<div style="font-size:12px;color:{DANGER};font-weight:500;margin-top:3px;">Overdue · {format_date(task["due_date"])}</div>'
        elif status == 'today':
            due_html = f'<div style="font-size:12px;color:{COLOR_TODAY};font-weight:500;margin-top:3px;">Due Today</div>'
        elif status == 'tomorrow':
            due_html = f'<div style="font-size:12px;color:{COLOR_TOMORROW};font-weight:500;margin-top:3px;">Due Tomorrow</div>'
        else:
            due_html = f'<div style="font-size:12px;color:{MUTED};margin-top:3px;">Due {format_date(task["due_date"])}</div>'

    # Tags
    cat_html = ''
    if task.get('category'):
        cat_html = f'<span style="display:inline-block;padding:2px 8px;background:#E8EDF8;border-radius:4px;font-size:11px;color:{NAVY};font-weight:600;font-family:\'DM Sans\',Arial,sans-serif;margin-top:4px;margin-right:4px;">{task["category"]}</span>'

    client_html = ''
    if task.get('client'):
        client_html = f'<span style="display:inline-block;padding:2px 8px;background:#FFF8E6;border:1px solid #E8C96A;border-radius:20px;font-size:11px;color:#6B4A00;font-weight:600;font-family:\'DM Sans\',Arial,sans-serif;margin-top:4px;margin-right:4px;">{task["client"]}</span>'

    # Recurrence label
    recur_html = ''
    if task.get('recurrence_type'):
        days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
        if task['recurrence_type'] == 'weekly' and task.get('recurrence_day') is not None:
            recur_html = f'<div style="font-size:11px;color:{NAVY};font-weight:500;margin-top:3px;">↻ Every {days[task["recurrence_day"]]}</div>'
        elif task['recurrence_type'] == 'monthly_end':
            recur_html = f'<div style="font-size:11px;color:{NAVY};font-weight:500;margin-top:3px;">↻ Monthly</div>'

    # Notes
    notes_html = ''
    if task.get('notes'):
        notes_html = f'<div style="font-size:12px;color:{MUTED};margin-top:6px;line-height:1.5;font-style:italic;">{task["notes"]}</div>'

    # Left border
    left_border = ''
    if status == 'overdue':
        left_border = f'border-left:3px solid {DANGER};'
    elif status == 'today':
        left_border = f'border-left:3px solid {GOLD};'
    elif status == 'tomorrow':
        left_border = f'border-left:3px solid #5B8FFF;'

    snooze_html = ''
    if snooze_url:
        snooze_html = f'''
        <tr>
          <td colspan="2" style="padding-top:8px;">
            <a href="{snooze_url}" style="font-size:12px;color:{MUTED};text-decoration:none;font-family:'DM Sans',Arial,sans-serif;">Snooze 1 day →</a>
          </td>
        </tr>'''

    tags_row = cat_html + client_html
    tags_html = f'<tr><td colspan="2" style="padding-top:2px;">{tags_row}</td></tr>' if tags_row else ''

    return f'''
    <tr>
      <td style="padding:0 0 8px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:{WHITE};border:1px solid {BORDER};border-radius:8px;{left_border}">
          <tr>
            <td style="padding:14px 16px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="font-size:15px;font-weight:600;color:{TEXT};font-family:'DM Sans',Arial,sans-serif;line-height:1.4;">
                    {task['task_name']}
                  </td>
                  <td align="right" style="white-space:nowrap;padding-left:16px;">
                    <a href="{complete_url}" style="display:inline-block;padding:6px 14px;background:{NAVY};color:{WHITE};text-decoration:none;border-radius:6px;font-size:12px;font-weight:700;font-family:'DM Sans',Arial,sans-serif;letter-spacing:0.3px;">DONE</a>
                  </td>
                </tr>
                {'<tr><td colspan="2">' + due_html + '</td></tr>' if due_html else ''}
                {tags_html}
                {'<tr><td colspan="2">' + recur_html + '</td></tr>' if recur_html else ''}
                {'<tr><td colspan="2">' + notes_html + '</td></tr>' if notes_html else ''}
                {snooze_html}
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>'''


def build_group_section(label, color, tasks):
    if not tasks:
        return ''
    rows = ''.join(build_task_row(t) for t in tasks)
    hdr = section_header(label, color, count=len(tasks))
    return f'''
      {hdr}
      <tr>
        <td style="padding:0 0 20px 0;">
          <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
        </td>
      </tr>'''


def build_email(tasks, send_type):
    today_str = get_mountain_now().strftime('%B %-d, %Y')
    time_label = '7am' if send_type == 'morning' else '4:30pm'
    skip_url = f"{PAGES_URL}/skip_followup.html"
    dow = get_mountain_dow()  # 0=Sun ... 6=Sat
    show_next_week = dow >= 3  # Wed, Thu, Fri, Sat

    # Group tasks
    groups = {
        'overdue':   [],
        'today':     [],
        'tomorrow':  [],
        'this_week': [],
        'next_week': [],
        'later':     [],
        'no_date':   []
    }

    for t in tasks:
        s = get_due_status(t.get('due_date'))
        groups[s].append(t)

    if not tasks:
        body_content = f'''
        <tr>
          <td align="center" style="padding:32px 0;color:{MUTED};font-size:14px;font-family:'DM Sans',Arial,sans-serif;">
            No open tasks.
          </td>
        </tr>'''
    else:
        body_content = (
            build_group_section('Overdue',       COLOR_OVERDUE,   groups['overdue'])   +
            build_group_section('Due Today',     COLOR_TODAY,     groups['today'])     +
            build_group_section('Due Tomorrow',  COLOR_TOMORROW,  groups['tomorrow'])  +
            build_group_section('Due This Week', COLOR_THIS_WEEK, groups['this_week'] if dow <= 4 else []) +
            (build_group_section('Due Next Week', COLOR_NEXT_WEEK, groups['next_week']) if show_next_week else '') +
            build_group_section('Coming Up',     COLOR_LATER,     groups['later'])     +
            build_group_section('No Due Date',   COLOR_NO_DATE,   groups['no_date'])
        )

    overdue_count = len(groups['overdue'])
    today_count = len(groups['today'])
    status_parts = []
    if overdue_count:
        status_parts.append(f'{overdue_count} overdue')
    if today_count:
        status_parts.append(f'{today_count} due today')
    status_str = ' · '.join(status_parts)

    skip_html = ''
    if send_type == 'morning':
        skip_html = f'''
          <tr>
            <td style="padding:24px 0 0 0;text-align:center;border-top:1px solid {BORDER};">
              <a href="{skip_url}" style="color:{MUTED};font-size:12px;text-decoration:none;font-family:'DM Sans',Arial,sans-serif;">
                Skip today's 4:30pm email
              </a>
            </td>
          </tr>'''

    return f'''
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:{BG};font-family:'DM Sans',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:24px 16px 32px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

          <tr>
            <td style="padding:0 0 20px 0;border-bottom:3px solid {NAVY};margin-bottom:24px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <div style="font-size:22px;font-weight:700;color:{NAVY};font-family:'DM Sans',Arial,sans-serif;letter-spacing:-0.5px;">Goodman Tasks</div>
                    <div style="font-size:13px;color:{MUTED};margin-top:3px;font-family:'DM Sans',Arial,sans-serif;">
                      {time_label} &nbsp;·&nbsp; {today_str} &nbsp;·&nbsp; {len(tasks)} open{f" &nbsp;·&nbsp; {status_str}" if status_str else ""}
                    </div>
                  </td>
                  <td align="right">
                    <div style="width:10px;height:10px;background:{GOLD};border-radius:50%;"></div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr><td style="height:20px;"></td></tr>

          {body_content}

          <tr>
            <td style="padding:16px 0 0 0;text-align:center;">
              <a href="{PAGES_URL}" style="color:{NAVY};font-size:13px;font-weight:600;text-decoration:none;font-family:'DM Sans',Arial,sans-serif;">Open Dashboard →</a>
            </td>
          </tr>

          {skip_html}

        </table>
      </td>
    </tr>
  </table>
</body>
</html>'''


def send_email(html, send_type, task_count):
    time_label = '7am' if send_type == 'morning' else '4:30pm'
    subject = f'Goodman Tasks · {time_label} · {task_count} open'
    if task_count == 0:
        subject = f'Goodman Tasks · {time_label} · All clear'

    res = requests.post(
        'https://api.resend.com/emails',
        headers={'Authorization': f'Bearer {RESEND_API_KEY}', 'Content-Type': 'application/json'},
        json={
            'from': 'onboarding@resend.dev',
            'to': [TO_EMAIL],
            'subject': subject,
            'html': html
        }
    )
    if res.status_code not in (200, 201):
        print(f'ERROR: Resend returned {res.status_code}: {res.text}')
        res.raise_for_status()
    else:
        print(f'SUCCESS: Email sent. Subject: {subject}')


def main():
    send_type = SEND_TYPE
    if send_type not in ('morning', 'followup'):
        print(f'STATUS: SEND_TYPE is "{send_type}" — must be morning or followup, exiting')
        return

    print(f'STATUS: Send type: {send_type}')

    if send_type == 'followup' and is_weekend():
        print('STATUS: Weekend — skipping followup email')
        return

    if send_type == 'followup' and check_followup_skipped():
        return

    if check_already_sent_today(send_type):
        return

    print('STATUS: Checking for tasks to unhide...')
    unhide_due_tasks()

    print('STATUS: Fetching tasks from Supabase...')
    tasks = fetch_tasks()
    print(f'STATUS: Found {len(tasks)} open visible tasks')

    html = build_email(tasks, send_type)
    send_email(html, send_type, len(tasks))
    mark_sent_today(send_type)


if __name__ == '__main__':
    main()
