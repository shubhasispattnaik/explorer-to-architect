import json, sys, os, time
from playwright.sync_api import sync_playwright

URL = 'file:///home/claude/e2a/test.html'
SHOTS = '/home/claude/e2a/shots'
os.makedirs(SHOTS, exist_ok=True)
DEVICES = {
    'phone': dict(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                  user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'),
    'laptop': dict(viewport={'width': 1366, 'height': 768}),
}
issues = []

def log(dev, msg):
    issues.append(f'[{dev}] {msg}')
    print(f'[{dev}] {msg}', flush=True)

OVERFLOW_JS = """() => { const W = document.documentElement.clientWidth; const out = [];
  if (document.documentElement.scrollWidth > W + 1) out.push('PAGE scrollWidth=' + document.documentElement.scrollWidth + ' > ' + W);
  document.querySelectorAll('#view *').forEach(e => { const r = e.getBoundingClientRect(); if (r.width && r.right > W + 1) {
    let p = e.parentElement, clipped = false; while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(auto|scroll|hidden)/.test(cs.overflowX)) { clipped = true; break; } p = p.parentElement; }
    if (!clipped) out.push((e.tagName + '.' + (e.className || '')).slice(0, 60) + ' right=' + Math.round(r.right)); } });
  return out.slice(0, 6); }"""

def check_overflow(page, dev, where):
    o = page.evaluate(OVERFLOW_JS)
    if o: log(dev, f'OVERFLOW at {where}: {o}')

def tap(page, loc, dev):
    loc.scroll_into_view_if_needed()
    if dev == 'phone': loc.tap()
    else: loc.click()

def go(page, h):
    page.evaluate(f"location.hash = '#{h}'")
    page.wait_for_timeout(120)

def run(dev):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(**DEVICES[dev])
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
        page.on('console', lambda m: errs.append('console.' + m.type + ': ' + m.text) if m.type in ('error',) and 'fonts.g' not in m.text and 'ERR_' not in m.text else None)
        page.goto(URL); page.wait_for_timeout(500)
        page.screenshot(path=f'{SHOTS}/{dev}_overview.png', full_page=False)
        check_overflow(page, dev, 'overview')
        pages = page.evaluate("Array.from(document.querySelectorAll('#mnav option')).map(o => o.value)")
        print(dev, 'pages:', len(pages), flush=True)
        # mobile nav select test
        if dev == 'phone':
            page.select_option('#mnav', 'plan'); page.wait_for_timeout(200)
            if not page.evaluate("location.hash") == '#plan': log(dev, 'mobile select nav did not navigate')
            vis = page.evaluate("getComputedStyle(document.querySelector('.rail')).display")
            if vis != 'none': log(dev, 'rail visible on phone')
        else:
            page.click('.rail a[href="#plan"]'); page.wait_for_timeout(200)
            if page.evaluate("location.hash") != '#plan': log(dev, 'rail link failed')
        # switch to instructor mode
        tap(page, page.locator('#modeI'), dev); page.wait_for_timeout(150)
        for h in pages:
            go(page, h)
            check_overflow(page, dev, h)
            if h.startswith('d'):
                tabs = page.locator('.tabs button')
                n = tabs.count()
                labels = [tabs.nth(i).get_attribute('data-t') for i in range(n)]
                if 'inst' not in labels: log(dev, f'{h}: no instructor tab in instructor mode')
                for i in range(n):
                    t = tabs.nth(i)
                    if not t.is_visible(): continue
                    tap(page, t, dev); page.wait_for_timeout(120)
                    check_overflow(page, dev, f'{h}/{labels[i]}')
                    if labels[i] == 'notes' and h in ('d2', 'd12'):
                        page.screenshot(path=f'{SHOTS}/{dev}_{h}_notes.png', full_page=False)
                    if labels[i] == 'inst' and h == 'd7':
                        page.screenshot(path=f'{SHOTS}/{dev}_{h}_inst.png', full_page=False)
                    if labels[i] == 'check':
                        qc = page.locator('.qcard').count()
                        for qi in range(qc):
                            btn = page.locator('.qcard').nth(qi).locator('.opt').first
                            tap(page, btn, dev)
                        page.wait_for_timeout(80)
                        if page.locator('.scorebox').count() != 1: log(dev, f'{h}: quiz scorebox missing after {qc} answers')
        prog = page.inner_text('#progTxt2')
        if '20 of 20' not in prog.lower(): log(dev, f'progress not full: {prog}')
        # back to trainee: instructor tab hidden
        tap(page, page.locator('#modeT'), dev); go(page, 'd3')
        if page.locator('.tabs button[data-t="inst"]').is_visible(): log(dev, 'instructor tab visible in trainee mode')
        print(dev, 'pages+quizzes done; errors so far:', errs[:5], flush=True)
        acts(page, dev)
        tests(page, dev)
        cert(page, dev)
        # persistence: reload keeps progress
        page.reload(); page.wait_for_timeout(400)
        if '20 of 20' not in page.inner_text('#progTxt2').lower(): log(dev, 'progress lost on reload')
        for e in errs: log(dev, 'JS ' + e)
        b.close()

def open_try(page, dev, h):
    go(page, h)
    tap(page, page.locator('.tabs button[data-t="try"]'), dev); page.wait_for_timeout(120)

def acts(page, dev):
    # d1 encounters
    open_try(page, dev, 'd1')
    for i in (0, 3, 5): tap(page, page.locator(f'#enc{i}'), dev)
    tap(page, page.get_by_role('button', name='Reveal'), dev)
    t = page.locator('.act').first.inner_text()
    if '2 of the 3 things' not in t: log(dev, 'encounters reveal text wrong: ' + t[-200:])
    # choice cards: click right/wrong on first card of each activity (sorter)
    cc = page.locator('.act').nth(1).locator('.ccard').first.locator('.chipbtn').first
    tap(page, cc, dev)
    if page.locator('.act').nth(1).locator('.fb').count() != 1: log(dev, 'sorter feedback missing')
    tap(page, page.locator('.act').nth(1).get_by_role('button', name='Reset'), dev)
    if page.locator('.act').nth(1).locator('.fb').count() != 0: log(dev, 'choiceCards reset failed')
    # d2 trainfilter
    open_try(page, dev, 'd2')
    if not page.locator('#tfGo').is_disabled(): log(dev, 'train enabled with no labels')
    tap(page, page.locator('#tfAuto'), dev); tap(page, page.locator('#tfGo'), dev)
    txt = page.locator('.act').first.inner_text()
    if '6/6' not in txt: log(dev, 'trainfilter honest labels did not get 6/6: ' + txt[-300:])
    # mislabel all
    for i in range(10):
        cur = page.locator(f'.chipbtn[data-i="{i}"][aria-pressed="true"]').get_attribute('data-v')
        other = '0' if cur == '1' else '1'
        tap(page, page.locator(f'.chipbtn[data-i="{i}"][data-v="{other}"]'), dev)
    tap(page, page.locator('#tfGo'), dev)
    txt = page.locator('.act').first.inner_text()
    if 'wrong label' not in txt: log(dev, 'trainfilter mislabel message missing')
    page.screenshot(path=f'{SHOTS}/{dev}_d2_try.png', full_page=False)
    # d3 layers
    open_try(page, dev, 'd3')
    for _ in range(3): tap(page, page.locator('#lyF'), dev)
    if page.locator('#lyOut').is_hidden(): log(dev, 'layers output not shown at stage 4')
    if not page.locator('#lyF').is_disabled(): log(dev, 'layers next not disabled at end')
    page.screenshot(path=f'{SHOTS}/{dev}_d3_layers.png', full_page=False)
    # d4 nextword + spot
    open_try(page, dev, 'd4')
    page.locator('#nwT').fill('0.1'); page.locator('#nwT').dispatch_event('input')
    tap(page, page.locator('#nwTen'), dev)
    low = int(page.inner_text('#nwDist'))
    tap(page, page.locator('#nwClr'), dev)
    page.locator('#nwT').fill('2'); page.locator('#nwT').dispatch_event('input')
    tap(page, page.locator('#nwTen'), dev); tap(page, page.locator('#nwTen'), dev)
    high = int(page.inner_text('#nwDist'))
    print(dev, 'nextword distinct low/high', low, high)
    if high <= low: log(dev, f'temperature not increasing variety: low {low} high {high}')
    for i in (2, 4, 6, 8): tap(page, page.locator(f'.sentence[data-i="{i}"]'), dev)
    tap(page, page.locator('.act').nth(1).get_by_role('button', name='Check'), dev)
    if 'caught 4 of 4' not in page.locator('.act').nth(1).inner_text(): log(dev, 'spot invention scoring wrong')
    # d5 safari
    open_try(page, dev, 'd5')
    for i in range(10):
        page.fill(f'#sf{i}a', f'App {i}'); page.select_option(f'#sf{i}b', str(1 + i % 5)); page.fill(f'#sf{i}c', 'user data')
    page.fill('#sfE', 'A spam filter learns from emails people mark.')
    if page.inner_text('#sfN') != '10': log(dev, 'safari count wrong ' + page.inner_text('#sfN'))
    tap(page, page.locator('#sfCopy'), dev); page.wait_for_timeout(100)
    if 'AI SAFARI JOURNAL' not in page.locator('.act').first.locator('pre').inner_text(): log(dev, 'safari copy text missing')
    # d7 craft
    open_try(page, dev, 'd7')
    page.select_option('#cEx', '14')
    if 'Strength: 5/5' not in page.inner_text('#cChk'): log(dev, 'craft example not 5/5: ' + page.inner_text('#cChk'))
    page.screenshot(path=f'{SHOTS}/{dev}_d7_craft.png', full_page=False)
    # d8 recipes copy
    open_try(page, dev, 'd8')
    tap(page, page.locator('.act').nth(1).get_by_role('button', name='Copy').first, dev); page.wait_for_timeout(150)
    # d10 portfolio
    open_try(page, dev, 'd10')
    page.fill('#pf0task', 'Budget with chat assistant'); page.select_option('#pfr0', '2')
    tap(page, page.locator('#pfCopy'), dev); page.wait_for_timeout(100)
    if 'Self-assessment: 2/10' not in page.locator('.act pre').inner_text(): log(dev, 'portfolio rubric total wrong')
    # d11 assistant
    open_try(page, dev, 'd11')
    page.select_option('#aEx', 'coach')
    for i in range(5): page.fill(f'#aT{i}', f'q{i}'); tap(page, page.locator(f'#aT{i}c'), dev)
    if page.locator('#aChk li.n').count() != 0: log(dev, 'assistant example not all checks: ' + page.inner_text('#aChk'))
    # d12 grounding
    open_try(page, dev, 'd12')
    expect = {'What attendance do I need to sit exams?': 'Section 3.1', 'When does the library open on Saturday?': 'Section 5.2',
              'Is there a late fee for paying fees after the deadline?': 'Section 2.4', 'What time do hostel gates close?': 'Section 7.1',
              'I lost my ID card, what do I do?': 'Section 8.2', 'What is the canteen menu on Friday?': 'couldn’t find', 'Who won the inter-college cricket match?': 'couldn’t find'}
    for q, e in expect.items():
        tap(page, page.locator(f'[data-q="{q}"]'), dev); page.wait_for_timeout(50)
        first_b = page.locator('#gChat .msg.b').first.inner_text()
        if e not in first_b: log(dev, f'grounding: "{q}" -> {first_b[:90]}')
    for q, e in {'re-exam fee?': 'Section 4.3', 'how do i get a scholarship': 'Section 6.1', 'wifi password': 'Section 9.1', 'is library open sunday': 'Section 5.2'}.items():
        page.fill('#gQ', q); page.press('#gQ', 'Enter'); page.wait_for_timeout(50)
        fb = page.locator('#gChat .msg.b').first.inner_text()
        if e not in fb: log(dev, f'grounding typed: "{q}" -> {fb[:90]}')
    tap(page, page.locator('#gOff'), dev)
    tap(page, page.locator('[data-q="What attendance do I need to sit exams?"]'), dev)
    if '60%' not in page.locator('#gChat .msg.b').first.inner_text(): log(dev, 'grounding off not hallucinating')
    page.screenshot(path=f'{SHOTS}/{dev}_d12_ground.png', full_page=False)
    # d13 workflow
    open_try(page, dev, 'd13')
    tap(page, page.locator('#wfClr'), dev)
    page.select_option('#wfT', '1')
    for s in ['sheet', 'aitotal', 'send', 'draft']: tap(page, page.locator(f'[data-add="{s}"]'), dev)
    tap(page, page.locator('#wfRun'), dev)
    t = page.inner_text('#wfOut')
    if '6/6' in t: log(dev, 'flawed workflow passed')
    tap(page, page.locator('#wfModel'), dev)
    if '6/6 checks pass' not in page.inner_text('#wfOut'): log(dev, 'model workflow not 6/6: ' + page.inner_text('#wfOut'))
    # reorder: move step 2 up
    tap(page, page.locator('[data-up="1"]'), dev); tap(page, page.locator('#wfRun'), dev)
    if '6/6' in page.inner_text('#wfOut'): log(dev, 'workflow reorder (total before sheet) still 6/6?')
    check_overflow(page, dev, 'd13 workflow')
    page.screenshot(path=f'{SHOTS}/{dev}_d13_wf.png', full_page=False)
    # d14 agent at level 2 reject send
    open_try(page, dev, 'd14')
    for _ in range(3): tap(page, page.get_by_role('button', name='Next step'), dev)
    tap(page, page.get_by_role('button', name='Approve'), dev)  # book room
    for _ in range(2): tap(page, page.get_by_role('button', name='Next step'), dev)
    tap(page, page.get_by_role('button', name='Next step'), dev)  # send -> approval
    if '442 people' not in page.inner_text('#agLog'): log(dev, 'agent approval did not show 442')
    tap(page, page.get_by_role('button', name='Reject and correct'), dev)
    tap(page, page.get_by_role('button', name='Approve'), dev)
    if 'caught the alumni mistake' not in page.inner_text('#agLog'): log(dev, 'agent level-2 outcome wrong: ' + page.inner_text('#agLog')[-200:])
    page.select_option('#agL', '3')
    for _ in range(6): tap(page, page.get_by_role('button', name='Next step'), dev)
    if '412 alumni were invited' not in page.inner_text('#agLog'): log(dev, 'agent level-4 no mistake shown')
    page.screenshot(path=f'{SHOTS}/{dev}_d14_agent.png', full_page=False)
    page.locator('#coN').fill('10'); page.locator('#coN').dispatch_event('input'); page.locator('#coR').fill('90'); page.locator('#coR').dispatch_event('input')
    if page.inner_text('#coP') != '35%': log(dev, 'compound wrong: ' + page.inner_text('#coP'))
    # d16 assemble
    open_try(page, dev, 'd16')
    for v in ['ui', 'model', 'know', 'human', 'eval', 'pay']: tap(page, page.locator(f'#asC input[value="{v}"]'), dev)
    tap(page, page.locator('#asGo'), dev)
    t = page.inner_text('#asOut')
    if '5/5 essentials · 1 over-built' not in t: log(dev, 'assemble result: ' + t[:120])
    # d17 cost
    open_try(page, dev, 'd17')
    c1 = page.inner_text('#cuC'); page.select_option('#cuM', 'large'); c2 = page.inner_text('#cuC')
    tap(page, page.locator('#cuG'), dev); c3 = page.inner_text('#cuC')
    print(dev, 'cost small/large/large+ground', c1, c2, c3)
    num = lambda s: int(s.replace('₹', '').replace(',', ''))
    if not (num(c1) < num(c2) < num(c3)): log(dev, f'cost ordering wrong {c1} {c2} {c3}')
    page.fill('#cuU', ''); page.wait_for_timeout(50)
    if 'NaN' in page.locator('.act').first.inner_text(): log(dev, 'cost NaN on empty users')
    # d18 evaluate
    open_try(page, dev, 'd18')
    exp = [1, 0, 1, 0, 1, 0, 1, 1]
    for i, v in enumerate(exp): tap(page, page.locator(f'.chipbtn[data-i="{i}"][data-v="{v}"]'), dev)
    tap(page, page.locator('#evGo'), dev)
    t = page.inner_text('#evOut')
    if '8/8' not in t or '63%' not in t or 'Not yet' not in t: log(dev, 'evaluate result: ' + t[:200])
    # d19 risk
    open_try(page, dev, 'd19')
    page.select_option('#rk0l', '2'); page.select_option('#rk0i', '2')
    if 'R1' not in page.locator('#rkM .c2').all_inner_texts().__str__(): log(dev, 'risk R1 not in red')
    if 'Control before launch' not in page.inner_text('#rkC'): log(dev, 'risk control list missing')
    check_overflow(page, dev, 'd19 risk')
    page.screenshot(path=f'{SHOTS}/{dev}_d19_risk.png', full_page=False)
    # d20 blueprint
    open_try(page, dev, 'd20')
    tap(page, page.locator('#kEx'), dev)
    for i in range(5): page.select_option(f'#kr{i}', '4')
    if page.inner_text('#kTot') != '20/20': log(dev, 'blueprint total wrong')
    # d15 builder
    open_try(page, dev, 'd15')
    for i in range(5): page.select_option(f'#bkr{i}', '2')
    if page.inner_text('#bkrT') != '10/10': log(dev, 'builder rubric total wrong')
    # examples page filters
    go(page, 'examples')
    tap(page, page.locator('[data-f="Law"]'), dev)
    if '1 of 20' not in page.inner_text('#exCount'): log(dev, 'examples filter Law: ' + page.inner_text('#exCount'))
    tap(page, page.locator('[data-l="3"]'), dev)
    if page.locator('.journey .st.on').count() != 1: log(dev, 'level highlight not applied')
    tap(page, page.locator('[data-f="All"]'), dev)
    check_overflow(page, dev, 'examples')
    page.screenshot(path=f'{SHOTS}/{dev}_examples.png', full_page=False)
    print(dev, 'activities done', flush=True)

def answer_correct(page, key):
    run = page.evaluate(f"JSON.parse(localStorage.getItem('e2a:run_{key}'))")
    for i, q in enumerate(run['qs']):
        page.locator(f'input[name="exq{i}"][value="{q["a"]}"]').check()
    return len(run['qs'])

def tests(page, dev):
    for key in ['t1', 't2', 't3', 't4', 'exam']:
        go(page, key)
        tap(page, page.locator('#exStart'), dev); page.wait_for_timeout(150)
        k = 'final' if key == 'exam' else key
        n = answer_correct(page, k)
        clock = page.inner_text('#exClock')
        if key == 't1':
            # leave and resume
            go(page, 'overview'); go(page, key)
            if page.locator('.resume-note').count() != 1: log(dev, 'test resume note missing')
            if page.locator('input[type=radio]:checked').count() != n: log(dev, 'answers not restored on resume')
            check_overflow(page, dev, 'test running')
            page.screenshot(path=f'{SHOTS}/{dev}_test_running.png', full_page=False)
        tap(page, page.locator('#exSubmit'), dev); page.wait_for_timeout(150)
        big = page.inner_text('.scorebox .big')
        if big != '100%': log(dev, f'{key}: score {big} with all correct answers (n={n})')
        if key == 'exam' and n != 30: log(dev, f'final has {n} questions')
    # unanswered confirm flow
    go(page, 't2'); tap(page, page.locator('#exAgain'), dev) if page.locator('#exAgain').count() else None
    tap(page, page.locator('#exStart'), dev)
    tap(page, page.locator('#exSubmit'), dev)
    if page.locator('.inline-confirm').count() != 1: log(dev, 'unanswered confirm missing')
    tap(page, page.get_by_role('button', name='Keep working'), dev)
    tap(page, page.locator('#exSubmit'), dev); tap(page, page.get_by_role('button', name='Submit now'), dev)
    if page.inner_text('.scorebox .big') != '0%': log(dev, 'empty submit not 0%')
    best = page.evaluate("JSON.parse(localStorage.getItem('e2a:tests')).t2.best")
    if best != 100: log(dev, 'best score overwritten by lower attempt')
    print(dev, 'tests done', flush=True)

def cert(page, dev):
    go(page, 'cert')
    tap(page, page.locator('#ctGo'), dev)
    if 'name' not in page.inner_text('#ctMsg'): log(dev, 'cert no-name message missing')
    page.fill('#ctName', 'Ananya Ramakrishnan Subramaniam Venkataraman')
    tap(page, page.locator('[data-mk="1"]'), dev)
    if 'Not yet' not in page.inner_text('[data-msg="1"]'): log(dev, 'badge created without practical')
    for n, v in [(1, '8'), (2, '7'), (3, '9'), (4, '18')]:
        page.fill(f'#pr{n}', v)
    page.fill('#pr2', '25'); page.wait_for_timeout(50)
    tap(page, page.locator('[data-mk="2"]'), dev)
    if 'Not yet' not in page.inner_text('[data-msg="2"]'): log(dev, 'badge accepted out-of-range practical 25/10')
    page.fill('#pr2', '7')
    for n in range(1, 5):
        tap(page, page.locator(f'[data-mk="{n}"]'), dev); page.wait_for_timeout(400)
        if page.locator(f'[data-out="{n}"] img').count() != 1: log(dev, f'badge {n} image missing: ' + page.inner_text(f'[data-msg="{n}"]'))
    if page.inner_text('#ctB') != '4/4': log(dev, 'badge count ' + page.inner_text('#ctB'))
    tap(page, page.locator('#ctGo'), dev); page.wait_for_timeout(600)
    if page.locator('#ctOut img').count() != 1: log(dev, 'certificate image missing: ' + page.inner_text('#ctMsg'))
    check_overflow(page, dev, 'cert')
    page.locator('#ctOut img').scroll_into_view_if_needed()
    page.screenshot(path=f'{SHOTS}/{dev}_cert.png', full_page=False)
    page.locator('[data-out="4"] img').scroll_into_view_if_needed()
    page.screenshot(path=f'{SHOTS}/{dev}_badge.png', full_page=False)
    # save images for visual check
    for sel, nm in [('#ctOut img', 'cert_img'), ('[data-out="4"] img', 'badge4_img'), ('[data-out="1"] img', 'badge1_img')]:
        src = page.get_attribute(sel, 'src')
        import base64
        open(f'{SHOTS}/{dev}_{nm}.png', 'wb').write(base64.b64decode(src.split(',')[1]))
    print(dev, 'cert done', flush=True)

for d in sys.argv[1:] or ['phone', 'laptop']:
    try:
        run(d)
    except Exception as e:
        log(d, 'EXCEPTION ' + repr(e)[:600])
print('\n==== ISSUES ====')
print('\n'.join(issues) or 'none')
