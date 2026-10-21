// 账单页逻辑：月份切换 + 分类可视化 + 记一笔/改/删 + AI 联动
const { request } = require('../../utils/request')
const { currentMonth, formatDate, formatMoney } = require('../../utils/util')

// 分类配色：图例、进度条、饼图共用一份，避免 WXML 里再写一长串三元表达式
const CAT_COLORS = {
  '餐饮': '#60768C', '购物': '#8797A7', '交通': '#A6B1BC',
  '生活': '#73897F', '娱乐': '#9B8974', '医疗': '#778A9A',
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
    cal: { cells: [], max: '', picked: false, pickedLabel: '', pickedAmount: '', pickedCount: 0 }
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
        plan: this._decoratePlan(month === currentMonth() ? plan : null),
        hasBills: list.length > 0,
        loading: false
      }, () => {
        this.drawPieChart(cats)   // canvas 节点要等这一帧渲染完才存在
        this._buildCal(list, month)
      })
      this.loadCheckin(month)
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

  // 画环形占比图
  drawPieChart(categories) {
    const cats = categories || this._pieCats
    if (!cats || !cats.length) return
    const ctx = wx.createCanvasContext('billPie', this)
    const total = cats.reduce((s, c) => s + c.amount, 0)
    const cx = 150, cy = 150, r = 132
    let start = -Math.PI / 2

    ctx.clearRect(0, 0, 300, 300)
    if (total <= 0) { ctx.draw(); return }
    cats.forEach(cat => {
      const angle = (cat.amount / total) * 2 * Math.PI
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.arc(cx, cy, r, start, start + angle)
      ctx.closePath()
      ctx.setFillStyle(cat.color || CAT_COLORS[cat.name] || '#B0A8A8')
      ctx.fill()
      start += angle
    })
    // 中心挖空成环形，并写上总额
    ctx.beginPath()
    ctx.arc(cx, cy, r * 0.6, 0, Math.PI * 2)
    ctx.setFillStyle('#FFFFFF')
    ctx.fill()
    ctx.setFillStyle('#7A8593')
    ctx.setFontSize(20)
    ctx.setTextAlign('center')
    ctx.fillText('本月支出', cx, cy - 12)
    ctx.setFillStyle('#1C2735')
    ctx.setFontSize(30)
    ctx.fillText(formatMoney(total) + ' 元', cx, cy + 26)
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
