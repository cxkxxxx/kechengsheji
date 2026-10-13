// 账单页逻辑：月份切换 + 分类可视化 + 记一笔/改/删 + AI 联动
const { request } = require('../../utils/request')
const { currentMonth, formatDate, formatMoney } = require('../../utils/util')

// 分类配色：图例、进度条、饼图共用一份，避免 WXML 里再写一长串三元表达式
const CAT_COLORS = {
  '餐饮': '#FF6B6B', '购物': '#4ECDC4', '交通': '#45B7D1',
  '生活': '#96CEB4', '娱乐': '#FFD93D', '医疗': '#C8A2C8',
  '其他': '#B0A8A8'
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
    form: { amount: '', category: '餐饮', source: '', bill_date: '' }
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
      }, () => this.drawPieChart(cats))   // canvas 节点要等这一帧渲染完才存在
    } catch (e) {
      this.setData({ loading: false })
      console.error(e)
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
    return Object.assign({}, plan, {
      budget_over: over,
      budget_overText: overText,
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
    ctx.setFillStyle('#8A90A6')
    ctx.setFontSize(20)
    ctx.setTextAlign('center')
    ctx.fillText('本月支出', cx, cy - 12)
    ctx.setFillStyle('#1E2233')
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
      form: { amount: '', category: '餐饮', source: '', bill_date: formatDate(new Date()) }
    })
  },

  openEditDialog(e) {
    const id = e.currentTarget.dataset.id
    const b = this.data.bills.filter(x => x.id === id)[0]
    if (!b) return
    this.setData({
      showDialog: true, dialogMode: 'edit', editingId: id,
      form: { amount: String(b.amount), category: b.category || '其他', source: b.source || '', bill_date: b.bill_date }
    })
  },

  closeAddDialog() { this.setData({ showDialog: false }) },

  onInput(e) { this.setData({ ['form.' + e.currentTarget.dataset.field]: e.detail.value }) },

  selectCategory(e) { this.setData({ 'form.category': e.currentTarget.dataset.cat }) },

  onDateChange(e) { this.setData({ 'form.bill_date': e.detail.value }) },

  async submitBill() {
    const { amount, category, source, bill_date } = this.data.form
    const value = parseFloat(amount)
    if (!(value > 0)) {
      wx.showToast({ title: '请输入大于 0 的金额', icon: 'none' })
      return
    }
    if (!bill_date) {
      wx.showToast({ title: '请选择日期', icon: 'none' })
      return
    }
    const payload = { amount: Math.round(value * 100) / 100, category, source, bill_date }
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

  // 导入演示账单
  seedDemo() {
    const that = this
    wx.showModal({
      title: '导入演示账单',
      content: '将用演示数据覆盖当前账号的全部账单，确认导入？',
      success(res) { if (res.confirm) that._doSeed() }
    })
  },

  async _doSeed() {
    this.setData({ seeding: true })
    try {
      await request('/bills/seed-demo', 'POST')
      wx.showToast({ title: '导入成功', icon: 'success' })
      this.setData({ month: currentMonth(), monthLabel: '本月 · ' + currentMonth(), isCurrentMonth: true })
      this.loadData(true)
    } catch (e) {
      wx.showToast({ title: '导入失败', icon: 'none' })
    } finally {
      this.setData({ seeding: false })
    }
  }
})
