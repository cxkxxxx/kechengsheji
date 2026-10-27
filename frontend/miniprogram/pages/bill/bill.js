// 账单页逻辑：月份切换 + 分类可视化 + 记一笔/改/删 + AI 联动
const { request } = require('../../utils/request')
const { currentMonth, formatDate, formatMoney } = require('../../utils/util')

// 分类配色：图例、进度条、环形图共用一份。
// 参考成熟记账 App 的做法用鲜亮的多彩色，占比图上一眼能区分；
// 餐饮固定绿色主视觉（正向色），其余按冷暖隔开避免相邻色混淆。
const CAT_COLORS = {
  '餐饮': '#18A775', '购物': '#4E8FF7', '交通': '#7C5CFC',
  '生活': '#EF7BAE', '娱乐': '#F2705F', '医疗': '#F5A623',
  '其他': '#C2C9D0'
}
const PREVIEW_COUNT = 8   // 列表默认只展示最近几笔，其余点开

function shiftMonthStr(month, delta) {
  const y = parseInt(month.slice(0, 4), 10)
  const m = parseInt(month.slice(5, 7), 10) + delta
  const ny = m < 1 ? y - 1 : (m > 12 ? y + 1 : y)
  const nm = m < 1 ? 12 : (m > 12 ? 1 : m)
  return ny + '-' + (nm < 10 ? '0' + nm : '' + nm)
}

Page({
  data: {
    month: '',
    monthLabel: '',
    isCurrentMonth: true,
    bills: [],
    shownBills: [],
    showAllBills: false,
    previewCount: PREVIEW_COUNT,
    months: [],
    summary: {},
    analysis: null,
    plan: null,
    hasBills: false,
    loading: true,
    adviceLoading: false,
    seeding: false,
    showDialog: false,
    dialogMode: 'add',
    editingId: 0,
    showGoalDialog: false,
    goalForm: { spend_limit: '', target_amount: '' },
    categories: ['餐饮', '购物', '交通', '生活', '娱乐', '医疗', '其他'],
    payChannels: ['微信支付', '支付宝', '云闪付', '京东支付', '美团支付'],
    form: { amount: '', category: '餐饮', source: '', pay_channel: '', order_no: '', bill_date: '' },
    // 每日打卡状态
    ck: { amount: '', note: '', cells: [], count: 0, checked: false, todaySaved: '', submitting: false },
    // 本月省钱记录明细（来源/备注/关联内容，长按可删）
    records: [],
    recordsTotal: 0,
    editingRecord: null,
    recForm: { amount: '', note: '' },
    // 快捷记账预置项：金额取常见真实价位，点一下就入账
    quickItems: [
      { label: '早餐', cat: '餐饮', amount: 8, ic: 'ic-wallet' },
      { label: '午餐', cat: '餐饮', amount: 20, ic: 'ic-wallet' },
      { label: '奶茶', cat: '餐饮', amount: 15, ic: 'ic-gift' },
      { label: '地铁', cat: '交通', amount: 5, ic: 'ic-link' },
      { label: '打车', cat: '交通', amount: 26, ic: 'ic-arrow' },
      { label: '日用品', cat: '购物', amount: 35, ic: 'ic-plus' }
    ],
    // 消费日历热力图
    cal: { cells: [], max: '', picked: false, pickedLabel: '', pickedAmount: '', pickedCount: 0 },
    // AI 月度解读：data=最近一次报告，list=历史报告（含当月筛选）
    report: { loading: false, data: null, empty: false, message: '', list: [] },
    // 近 6 个月支出趋势（柱状图）
    trend: { labels: [], values: [] }
  },

  onLoad() {
    const month = currentMonth()
    this.setData({ month, monthLabel: this._label(month), isCurrentMonth: true })
    this.loadData()
  },

  // 从助手页记账后切回来要能看到新账
  onShow() {
    if (this._loadedOnce) this.loadData()
    this._loadedOnce = true
  },

  onPullDownRefresh() {
    this.loadData(true).then(() => wx.stopPullDownRefresh()).catch(() => wx.stopPullDownRefresh())
  },

  _label(month) {
    if (month === currentMonth()) return '本月 · ' + month
    const prev = shiftMonthStr(currentMonth(), -1)
    if (month === prev) return '上月 · ' + month
    return month
  },

  async loadData(force = false) {
    const month = this.data.month
    this.setData({ loading: true })
    try {
      const jobs = [
        request('/bills?month=' + month, 'GET', {}, force),
        request('/bills/summary?month=' + month, 'GET', {}, force),
        request('/bills/analysis?month=' + month + '&need_advice=0', 'GET', {}, force),
        request('/bills/months', 'GET', {}, force)
      ]
      // 省钱目标只针对当月有意义，翻到别的月份就不查，避免显示对不上的数字
      if (month === currentMonth()) jobs.push(request('/checkin/plan', 'GET', {}, force))
      const [bills, summary, analysis, months, plan] = await Promise.all(jobs)

      const list = (bills || []).map(b => Object.assign({}, b, {
        color: CAT_COLORS[b.category] || '#B0A8A8'
      }))
      const cats = ((analysis && analysis.categories) || []).map(c => ({
        name: c.name, amount: c.amount, pct: c.pct, count: c.count,
        color: CAT_COLORS[c.name] || '#B0A8A8'
      }))
      const view = Object.assign({}, analysis || {}, { categories: cats })

      // 近 6 个月趋势：/bills/months 本来就带每个月的 total，
      // 没数据的月份补 0（0 是真实的「没花」，不是编的），最后一个月 = 当前查看的月份
      const monthsArr = months || []
      const tLabels = [], tValues = []
      for (let i = 5; i >= 0; i--) {
        const m = shiftMonthStr(month, -i)
        const hit = monthsArr.filter(x => x.month === m)[0]
        tLabels.push(parseInt(m.slice(5), 10) + '月')
        tValues.push(hit ? (parseFloat(hit.total) || 0) : 0)
      }

      this.setData({
        bills: list,
        shownBills: list.slice(0, PREVIEW_COUNT),
        showAllBills: false,
        summary: Object.assign({}, summary || {}, {
          totalText: formatMoney(summary && summary.total),
          categories: Object.keys((summary && summary.categories) || {}).map(k => ({
            name: k,
            value: parseFloat(summary.categories[k]) || 0,
            color: CAT_COLORS[k] || '#B0A8A8'
          })).sort((a, b) => b.value - a.value).map(c => Object.assign({}, c, {
            amount: formatMoney(c.value)
          }))
        }),
        analysis: view,
        months: months || [],
        trend: { labels: tLabels, values: tValues },
        plan: this._decoratePlan(month === currentMonth() ? plan : null),
        hasBills: list.length > 0,
        loading: false
      }, () => {
        this.drawPieChart(cats)   // canvas 节点要等这一帧渲染完才存在
        this.drawTrend()
        this._buildCal(list, month)
      })
      this.loadCheckin(month)
      this.loadRecords(month)
      this.loadReportList(month)
    } catch (e) {
      this.setData({ loading: false })
      console.error(e)
    }
  },

  // 消费日历热力图：直接把已加载的账单按天聚合，不用多打一次接口
  _buildCal(list, month) {
    const byDay = {}
    ;(list || []).forEach(b => {
      const d = parseInt(String(b.bill_date || '').slice(8, 10), 10)
      if (!d) return
      byDay[d] = byDay[d] || { amount: 0, count: 0 }
      byDay[d].amount += parseFloat(b.amount) || 0
      byDay[d].count += 1
    })
    const y = parseInt(month.slice(0, 4), 10)
    const m = parseInt(month.slice(5, 7), 10)
    const dim = new Date(y, m, 0).getDate()
    const lead = new Date(y, m - 1, 1).getDay()     // 当月 1 号前面空几格（周日开头）
    const vals = Object.keys(byDay).map(k => byDay[k].amount)
    const max = vals.length ? Math.max.apply(null, vals) : 0

    const cells = []
    for (let i = 0; i < lead; i++) cells.push({ key: 'e' + i, day: 0, cls: 'cal-empty', short: '' })
    for (let d = 1; d <= dim; d++) {
      const v = byDay[d] ? byDay[d].amount : 0
      // 分四档上色，用「占峰值的比例」而不是绝对金额，换个月份也能横向比较
      let cls = v > 0 ? 'cal-l1' : 'cal-l0'
      if (max > 0 && v > 0) {
        const r = v / max
        cls = r > 0.66 ? 'cal-l4' : r > 0.33 ? 'cal-l3' : r > 0.12 ? 'cal-l2' : 'cal-l1'
      }
      cells.push({ key: 'd' + d, day: d, cls, short: v >= 1000 ? (v / 1000).toFixed(1) + 'k' : (v ? Math.round(v) : '') })
    }
    this.setData({
      'cal.cells': cells,
      'cal.max': max ? formatMoney(max) : '—',
      'cal.picked': false, 'cal.pickedLabel': '', 'cal.pickedAmount': '', 'cal.pickedCount': 0
    })
  },

  pickCalDay(e) {
    const d = e.currentTarget.dataset.day
    if (!d) return
    const month = this.data.month
    const rows = this.data.bills.filter(b =>
      String(b.bill_date).slice(0, 10) === month + '-' + (d < 10 ? '0' + d : d))
    const sum = rows.reduce((s, b) => s + (parseFloat(b.amount) || 0), 0)
    this.setData({
      cal: Object.assign({}, this.data.cal, {
        picked: true,
        pickedLabel: month.slice(5) + '月' + d + '日',
        pickedAmount: formatMoney(sum) + ' 元',
        pickedCount: rows.length
      })
    })
  },

  // 打卡：拉本月明细，用来渲染日历格子和高亮「今天已打」
  async loadCheckin(month) {
    if (month !== currentMonth()) {
      this.setData({ 'ck.cells': [], 'ck.count': 0, 'ck.checked': false })
      return
    }
    try {
      const d = await request('/checkin/month?month=' + month, 'GET')
      const done = {}
      ;(d.days || []).forEach(x => { done[x.day] = x })
      const now = new Date()
      const dim = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()
      const cells = []
      for (let i = 1; i <= dim; i++) {
        cells.push({
          key: i, day: i,
          cls: done[i] ? 'ck-on' : (i < now.getDate() ? 'ck-miss' : 'ck-off'),
          saved: done[i] ? formatMoney(done[i].saved_amount) : ''
        })
      }
      this.setData({
        'ck.cells': cells,
        'ck.count': d.count || 0,
        'ck.checked': !!d.checked_today,
        'ck.todaySaved': done[now.getDate()] ? formatMoney(done[now.getDate()].saved_amount) + ' 元' : ''
      })
    } catch (e) { console.error(e) }
  },

  onCkAmount(e) { this.setData({ 'ck.amount': e.detail.value }) },
  onCkNote(e) { this.setData({ 'ck.note': e.detail.value }) },

  // 本月省钱记录：打卡/攻略/社区经验/AI方案 都在这份流水里，长按可删
  async loadRecords(month) {
    try {
      const d = await request('/checkin/records?month=' + month, 'GET')
      this.setData({
        records: (d.records || []).map(r => Object.assign({}, r, {
          amountText: formatMoney(r.saved_amount),
          dayShort: r.day.slice(5),
          // 备注和来源内容拼成一行副标题，别让列表行太高
          subText: [r.note, r.ref_title ? '来自「' + r.ref_title + '」' : ''].filter(Boolean).join(' · ')
        })),
        recordsTotal: formatMoney(d.total || 0)
      })
    } catch (e) { console.error(e) }
  },

  onRecInput(e) {
    this.setData({ ['recForm.' + e.currentTarget.dataset.field]: e.detail.value })
  },

  openRecordEdit(e) {
    const id = e.currentTarget.dataset.id
    const r = this.data.records.filter(x => x.id === id)[0]
    if (!r) return
    this.setData({
      editingRecord: r,
      recForm: { amount: String(r.saved_amount), note: r.note || '' }
    })
  },

  closeRecordEdit() { this.setData({ editingRecord: null }) },

  async saveRecordEdit() {
    const r = this.data.editingRecord
    if (!r) return
    const v = parseFloat(this.data.recForm.amount)
    if (!(v > 0)) {
      wx.showToast({ title: '金额要大于 0', icon: 'none' })
      return
    }
    try {
      await request('/checkin/records/' + r.id, 'PUT', {
        saved_amount: Math.round(v * 100) / 100,
        note: this.data.recForm.note || ''
      })
      this.setData({ editingRecord: null })
      wx.showToast({ title: '已更新', icon: 'success' })
      this.loadData(true)
    } catch (e) {
      wx.showToast({ title: e.message || '更新失败', icon: 'none' })
    }
  },

  removeRecord(e) {
    const id = e.currentTarget.dataset.id
    const r = this.data.records.filter(x => x.id === id)[0]
    const that = this
    wx.showModal({
      title: '删除这条省钱记录？',
      content: r ? (r.day + ' · ' + formatMoney(r.saved_amount) + ' 元' + (r.note ? ' · ' + r.note : '')) : '',
      confirmText: '删除', confirmColor: '#FF6B6B',
      success(res) {
        if (!res.confirm) return
        request('/checkin/records/' + id, 'DELETE').then(() => {
          wx.showToast({ title: '已删除', icon: 'success' })
          that.loadData(true)   // 月度累计和总节省都由后端重算，前端整体刷
        }).catch(err => console.error(err))
      }
    })
  },

  // ---------- AI 月度解读：金额统计由后端程序算好，AI 只写解读 ----------
  loadReportList(month) {
    // 换月份就切到那个月的历史报告；当前展示的报告不属于这个月就收起来
    request('/ai/bill-reports?month=' + month, 'GET').then(d => {
      const list = (d.items || []).map(r => Object.assign({}, r, {
        label: r.month + ' · ' + (r.created_at || '')
      }))
      this.setData({
        'report.list': list,
        'report.data': (this.data.report.data && this.data.report.data.month === month)
          ? this.data.report.data : null,
        'report.empty': false, 'report.message': ''
      })
    }).catch(e => console.error(e))
  },

  async makeReport() {
    if (this.data.report.loading) return
    this.setData({ 'report.loading': true, 'report.empty': false, 'report.message': '' })
    try {
      const d = await request('/ai/bill-report', 'POST', { month: this.data.month }, true)
      if (d.empty) {
        this.setData({ 'report.loading': false, 'report.empty': true, 'report.message': d.message || '' })
      } else {
        this.setData({
          report: Object.assign({}, this.data.report, { loading: false, data: d, empty: false })
        })
        this.loadReportList(this.data.month)
      }
    } catch (e) {
      this.setData({ 'report.loading': false })
    }
  },

  pickReport(e) {
    const it = this.data.report.list[e.detail.value]
    if (!it) return
    request('/ai/bill-reports/' + it.id, 'GET').then(d => {
      this.setData({ 'report.data': d })
    }).catch(err => console.error(err))
  },

  // 带着报告结论去 AI 助手追问（问答走已有的 agent，不另起接口）
  askReportAI() {
    const d = this.data.report.data
    const s = (d && d.stats) || {}
    const app = getApp()
    app.globalData.pendingAsk = {
      agent: 'budget',
      question: '刚看了 ' + (d ? d.month : this.data.month) + ' 的 AI 解读，本月总支出 '
        + formatMoney(s.total || 0) + ' 元。帮我详细说说：本月主要开销在哪，哪些分类和上月比变化最大，预算该怎么调？'
    }
    wx.switchTab({ url: '/pages/assistant/assistant' })
  },

  async submitCheckin() {
    if (this.data.ck.submitting) return
    const v = parseFloat(this.data.ck.amount)
    if (!(v > 0)) {
      wx.showToast({ title: '请填写今天省了多少元', icon: 'none' })
      return
    }
    this.setData({ 'ck.submitting': true })
    try {
      const r = await request('/checkin/do', 'POST', { saved_amount: v, note: this.data.ck.note || '' })
      wx.showToast({ title: r && r.repeated ? '已更新今天' : '打卡成功', icon: 'success' })
      this.setData({ 'ck.amount': '', 'ck.note': '', 'ck.submitting': false })
      this.loadData(true)
    } catch (e) {
      this.setData({ 'ck.submitting': false })
      wx.showToast({ title: e.message || '打卡失败', icon: 'none' })
    }
  },

  // 快捷记账：点一下就按默认金额入账。后端 POST /bills 是现成的，不用新接口。
  async quickAdd(e) {
    if (this._quickBusy) return
    const it = this.data.quickItems[e.currentTarget.dataset.i]
    if (!it) return
    this._quickBusy = true
    try {
      await request('/bills', 'POST', {
        amount: it.amount, category: it.cat, source: it.label,
        bill_date: formatDate(new Date())
      })
      wx.showToast({ title: '已记 ' + it.label + ' ¥' + it.amount, icon: 'success' })
      this.loadData(true)
    } catch (err) {
      wx.showToast({ title: err.message || '记录失败', icon: 'none' })
    } finally {
      setTimeout(() => { this._quickBusy = false }, 400)
    }
  },

  // 后端给数字，这里只补「怎么显示」：超预算要变红并说清超了多少
  _decoratePlan(plan) {
    if (!plan) return null
    const limit = parseFloat(plan.spend_limit) || 0
    const spend = parseFloat(plan.spend) || 0
    const over = limit > 0 && spend > limit
    let overText = ''
    if (limit > 0) {
      overText = over
        ? '已超支 ' + formatMoney(spend - limit) + ' 元'
        : '还可花 ' + formatMoney(limit - spend) + ' 元'
    }
    // 「每天还能花多少」：只有看的是本月、且没超支时才有意义
    const now = new Date()
    const viewing = this.data.month || currentMonth()
    const isNow = viewing === currentMonth()
    const dim = new Date(parseInt(viewing.slice(0, 4), 10),
                         parseInt(viewing.slice(5, 7), 10), 0).getDate()
    const daysLeft = isNow ? Math.max(0, dim - now.getDate()) : 0
    let perDay = ''
    if (limit > 0 && isNow && !over && daysLeft > 0) {
      perDay = '剩 ' + daysLeft + ' 天，每天可花 ' + formatMoney((limit - spend) / daysLeft) + ' 元'
    } else if (limit > 0 && isNow && !over) {
      perDay = '今天是本月最后一天'
    }
    return Object.assign({}, plan, {
      budget_over: over,
      budget_overText: overText,
      budget_perDay: perDay,
      budget_left: limit > 0 ? formatMoney(Math.max(0, limit - spend)) : '',
      budget_overAmt: over ? formatMoney(spend - limit) : '',
      days_left: daysLeft,
      spend: formatMoney(spend),
      saved_amount: formatMoney(plan.saved_amount)
    })
  },

  openGoalDialog() {
    const p = this.data.plan || {}
    this.setData({
      showGoalDialog: true,
      goalForm: {
        spend_limit: p.spend_limit ? String(p.spend_limit) : '',
        target_amount: p.target_amount ? String(p.target_amount) : ''
      }
    })
  },

  closeGoalDialog() { this.setData({ showGoalDialog: false }) },

  onGoalInput(e) {
    const f = e.currentTarget.dataset.field
    this.setData({ ['goalForm.' + f]: e.detail.value })
  },

  async saveGoal() {
    const limit = parseFloat(this.data.goalForm.spend_limit) || 0
    const target = parseFloat(this.data.goalForm.target_amount) || 0
    if (limit <= 0 && target <= 0) {
      wx.showToast({ title: '至少设一个目标', icon: 'none' })
      return
    }
    if (limit < 0 || target < 0) {
      wx.showToast({ title: '目标不能是负数', icon: 'none' })
      return
    }
    try {
      const plan = await request('/checkin/plan', 'POST', { spend_limit: limit, target_amount: target })
      this.setData({ plan: this._decoratePlan(plan), showGoalDialog: false })
      wx.showToast({ title: '目标已保存', icon: 'success' })
    } catch (e) { console.error(e) }
  },

  // 切换上一/下一月
  shiftMonth(e) {
    const delta = parseInt(e.currentTarget.dataset.d, 10)
    const month = shiftMonthStr(this.data.month, delta)
    if (month > currentMonth()) {
      wx.showToast({ title: '还没有到那个月', icon: 'none' })
      return
    }
    this.setData({ month, monthLabel: this._label(month), isCurrentMonth: month === currentMonth() })
    this.loadData()
  },

  pickMonth(e) {
    const month = this.data.months[e.detail.value] && this.data.months[e.detail.value].month
    if (!month || month === this.data.month) return
    this.setData({ month, monthLabel: this._label(month), isCurrentMonth: month === currentMonth() })
    this.loadData()
  },

  toggleBills() {
    const all = !this.data.showAllBills
    this.setData({ showAllBills: all, shownBills: all ? this.data.bills : this.data.bills.slice(0, PREVIEW_COUNT) })
  },

  // 手动刷新 AI 建议（此时才调 LLM，省 token）
  async refreshAdvice() {
    if (this.data.adviceLoading) return
    this.setData({ adviceLoading: true })
    try {
      const data = await request('/bills/analysis?month=' + this.data.month + '&need_advice=1')
      if (data && data.ai_advice) {
        const cats = (data.categories || []).map(c => ({
          name: c.name, amount: c.amount, pct: c.pct, count: c.count,
          color: CAT_COLORS[c.name] || '#B0A8A8'
        }))
        this.setData({ 'analysis.ai_advice': data.ai_advice, 'analysis.categories': cats },
          () => this.drawPieChart(cats))
        wx.showToast({ title: '建议已更新', icon: 'success' })
      }
    } catch (e) {
      wx.showToast({ title: '生成失败，请重试', icon: 'none' })
      console.error(e)
    } finally {
      this.setData({ adviceLoading: false })
    }
  },

  // 画分类占比环形图：留缝的分段圆环 + 环外百分比标签 + 中心总额
  drawPieChart(categories) {
    const cats = categories || this._pieCats
    if (!cats || !cats.length) return
    this._pieCats = cats
    const ctx = wx.createCanvasContext('billPie', this)
    const total = cats.reduce((s, c) => s + c.amount, 0)
    const cx = 150, cy = 150, r = 108
    let start = -Math.PI / 2

    ctx.clearRect(0, 0, 300, 300)
    if (total <= 0) { ctx.draw(); return }
    cats.forEach(cat => {
      const frac = cat.amount / total
      const angle = frac * 2 * Math.PI
      if (frac > 0) {
        // 段与段之间留一道白缝，比实心圆环精致
        const pad = cats.length > 1 ? 0.016 : 0
        ctx.beginPath()
        ctx.moveTo(cx, cy)
        ctx.arc(cx, cy, r, start + pad, start + angle - pad)
        ctx.closePath()
        ctx.setFillStyle(cat.color || CAT_COLORS[cat.name] || '#C2C9D0')
        ctx.fill()
        // 占比够大的分段才标百分比，太小的会互相叠字
        if (frac >= 0.05) {
          const mid = start + angle / 2
          ctx.setFillStyle('#536171')
          ctx.setFontSize(11)
          ctx.setTextAlign('center')
          ctx.fillText(Math.round(frac * 100) + '%',
            cx + Math.cos(mid) * (r + 20), cy + Math.sin(mid) * (r + 20) + 4)
        }
      }
      start += angle
    })
    // 中心挖空成环形，并写上总额
    ctx.beginPath()
    ctx.arc(cx, cy, r * 0.62, 0, Math.PI * 2)
    ctx.setFillStyle('#FFFFFF')
    ctx.fill()
    ctx.setFillStyle('#7A8593')
    ctx.setFontSize(19)
    ctx.setTextAlign('center')
    ctx.fillText('本月支出', cx, cy - 12)
    ctx.setFillStyle('#1C2735')
    ctx.setFontSize(28)
    ctx.fillText(formatMoney(total) + ' 元', cx, cy + 24)
    ctx.draw()
  },

  // 近 6 个月支出柱状图：绿色圆角柱 + 月均虚线，当月加深
  drawTrend() {
    const t = this.data.trend
    if (!t || !t.values || !t.values.length) return
    const ctx = wx.createCanvasContext('trendBars', this)
    const info = wx.getSystemInfoSync()
    // 画布 CSS 宽是撑满卡片的，这里算出同样的像素宽：页边距 24rpx×2 + 卡片内边距 32rpx×2 = 56px
    const W = Math.max(240, info.windowWidth - 56)
    const H = 150
    const padL = 36, padR = 6, padT = 12, padB = 20
    const plotW = W - padL - padR, plotH = H - padT - padB
    const vals = t.values

    // 纵轴取「好看的」4 段刻度，不硬凑 max
    let step = 1
    const maxV = Math.max.apply(null, vals.concat([0]))
    if (maxV > 0) {
      const raw = maxV / 4
      const mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10))
      const n = raw / mag
      step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag
    }
    const top = step * 4

    ctx.clearRect(0, 0, W, H)
    // 网格线 + 刻度
    for (let k = 0; k <= 4; k++) {
      const y = padT + plotH - plotH * k * step / (top || 1)
      ctx.setStrokeStyle('#EEF1F5')
      ctx.setLineWidth(1)
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke()
      ctx.setFillStyle('#A6ACBE')
      ctx.setFontSize(10)
      ctx.setTextAlign('right')
      const v = k * step
      ctx.fillText(v >= 1000 ? (v / 1000) + 'k' : '' + Math.round(v), padL - 6, y + 3)
    }

    // 柱子：最后一根（正在看的月份）加深
    const slot = plotW / 6
    const bw = Math.min(26, slot * 0.44)
    vals.forEach((v, i) => {
      const h = top > 0 ? plotH * v / top : 0
      const x = padL + slot * i + (slot - bw) / 2
      const y = padT + plotH - h
      ctx.setFillStyle(i === vals.length - 1 ? '#0E7A55' : '#18A775')
      const rAdj = Math.min(5, h / 2)
      ctx.beginPath()
      ctx.moveTo(x, padT + plotH)
      ctx.lineTo(x, y + rAdj)
      ctx.quadraticCurveTo(x, y, x + rAdj, y)
      ctx.lineTo(x + bw - rAdj, y)
      ctx.quadraticCurveTo(x + bw, y, x + bw, y + rAdj)
      ctx.lineTo(x + bw, padT + plotH)
      ctx.closePath()
      ctx.fill()
      ctx.setFillStyle(i === vals.length - 1 ? '#1C2735' : '#7A8593')
      ctx.setFontSize(10)
      ctx.setTextAlign('center')
      ctx.fillText(t.labels[i], x + bw / 2, H - 6)
    })

    // 月均线：只对有数据的月份求平均，全是 0 就不画
    const nz = vals.filter(v => v > 0)
    if (nz.length > 1) {
      const avg = nz.reduce((s, v) => s + v, 0) / nz.length
      if (avg <= top) {
        const y = padT + plotH - plotH * avg / top
        ctx.setStrokeStyle('#F5A623')
        ctx.setLineWidth(1)
        ctx.setLineDash([4, 4])
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke()
        ctx.setLineDash([])
        ctx.setFillStyle('#F5A623')
        ctx.setTextAlign('left')
        ctx.setFontSize(9)
        ctx.fillText('月均 ¥' + (avg >= 1000 ? (avg / 1000).toFixed(1) + 'k' : Math.round(avg)), padL + 2, y - 4)
      }
    }
    ctx.draw()
  },

  // 把当前月份的真实账单交给 AI 助手分析
  askAI() {
    const app = getApp()
    const a = this.data.analysis || {}
    let q = '帮我分析 ' + this.data.month + ' 的账单，给出这个月能落地的省钱建议'
    if (a.total > 0) q += '（总支出 ' + formatMoney(a.total) + ' 元' + (a.diff > 0 ? '，比上月多花 ' + formatMoney(a.diff) + ' 元' : '') + '）'
    if (app && app.globalData) app.globalData.pendingAsk = { question: q, agent: 'budget' }
    wx.switchTab({ url: '/pages/assistant/assistant' })
  },

  openAddDialog() {
    this.setData({
      showDialog: true, dialogMode: 'add', editingId: 0,
      form: { amount: '', category: '餐饮', source: '', pay_channel: '', order_no: '',
              bill_date: formatDate(new Date()) }
    })
  },

  openEditDialog(e) {
    const id = e.currentTarget.dataset.id
    const b = this.data.bills.filter(x => x.id === id)[0]
    if (!b) return
    this.setData({
      showDialog: true, dialogMode: 'edit', editingId: id,
      form: { amount: String(b.amount), category: b.category || '其他', source: b.source || '',
              pay_channel: b.pay_channel || '', order_no: b.order_no || '', bill_date: b.bill_date }
    })
  },

  closeAddDialog() { this.setData({ showDialog: false }) },

  onInput(e) { this.setData({ ['form.' + e.currentTarget.dataset.field]: e.detail.value }) },

  selectCategory(e) { this.setData({ 'form.category': e.currentTarget.dataset.cat }) },

  // 再点一次已选中的渠道就取消（手打的账本来就没有平台）
  selectChannel(e) {
    const ch = e.currentTarget.dataset.ch
    this.setData({ 'form.pay_channel': this.data.form.pay_channel === ch ? '' : ch })
  },

  onDateChange(e) { this.setData({ 'form.bill_date': e.detail.value }) },

  async submitBill() {
    const { amount, category, source, pay_channel, order_no, bill_date } = this.data.form
    const value = parseFloat(amount)
    if (!(value > 0)) {
      wx.showToast({ title: '请输入大于 0 的金额', icon: 'none' })
      return
    }
    if (!bill_date) {
      wx.showToast({ title: '请选择日期', icon: 'none' })
      return
    }
    const payload = {
      amount: Math.round(value * 100) / 100, category, source, bill_date,
      pay_channel: pay_channel || '', order_no: order_no || ''
    }
    try {
      if (this.data.dialogMode === 'edit') {
        await request('/bills/' + this.data.editingId, 'PUT', payload)
        wx.showToast({ title: '已更新', icon: 'success' })
      } else {
        await request('/bills', 'POST', payload)
        wx.showToast({ title: '记录成功', icon: 'success' })
      }
      this.closeAddDialog()
      this.loadData(true)
    } catch (e) { console.error(e) }
  },

  removeBill(e) { this._confirmDelete(e.currentTarget.dataset.id) },

  deleteFromDialog() {
    this.closeAddDialog()
    this._confirmDelete(this.data.editingId)
  },

  _confirmDelete(id) {
    if (!id) return
    const b = this.data.bills.filter(x => x.id === id)[0]
    const that = this
    wx.showModal({
      title: '删除这笔账单？',
      content: b ? ((b.source || b.category) + ' · ' + b.amount + ' 元') : '',
      confirmText: '删除', confirmColor: '#FF6B6B',
      success(res) {
        if (!res.confirm) return
        request('/bills/' + id, 'DELETE').then(() => {
          wx.showToast({ title: '已删除', icon: 'success' })
          that.loadData(true)
        }).catch(err => console.error(err))
      }
    })
  },

  // 导入演示账单：可以只灌当前正在看的这个月，也可以一次补齐近 4 个月。
  // 后端只会清掉它要写入的那几个月，其它月份用户自己记的账不受影响。
  seedDemo() {
    const that = this
    const cur = this.data.month || currentMonth()
    wx.showActionSheet({
      itemList: [
        '只导入 ' + cur + '（当前查看的月份）',
        '补齐近 4 个月（含本月，环比才有数据可比）'
      ],
      success(res) {
        if (res.tapIndex === 0) that._doSeed(cur, 1)
        else that._doSeed(currentMonth(), 4)
      }
    })
  },

  async _doSeed(month, months) {
    this.setData({ seeding: true })
    try {
      const r = await request('/bills/seed-demo?month=' + month + '&months=' + (months || 1), 'POST')
      wx.showToast({ title: (r && r.imported ? r.imported + ' 条' : '已导入'), icon: 'success' })
      // 停在用户当前看的那个月，不要每次导入都跳回本月
      const keep = month || currentMonth()
      this.setData({
        month: keep,
        monthLabel: this._label(keep),
        isCurrentMonth: keep === currentMonth()
      })
      this.loadData(true)
    } catch (e) {
      wx.showToast({ title: '导入失败', icon: 'none' })
    } finally {
      this.setData({ seeding: false })
    }
  }
})
