// 首页：标题 → 快捷功能 → 本月省钱概览(含目标) → 消费日历 → 最近消费 → 精选攻略
// 页面级滚动（无嵌套 scroll-view），下拉刷新走 onPullDownRefresh
const { request } = require('../../utils/request')
const { fullUrl, formatMoney, currentMonth, formatDate } = require('../../utils/util')

const PAGE = 8 // 精选攻略每屏固定显示条数，下拉轮换
const CAT_COLORS = {
  '餐饮': '#18A775', '购物': '#4E8FF7', '交通': '#7C5CFC',
  '生活': '#EF7BAE', '娱乐': '#F2705F', '医疗': '#F5A623',
  '其他': '#C2C9D0'
}

function fmt(v) { return formatMoney(parseFloat(v) || 0) }

Page({
  data: {
    loggedIn: false,
    month: '',
    monthText: '',
    // 本月省钱概览（支出 / 实际节省 / 预算状态）+ 目标（目标金额 / 还差 / 进度），一份后端口径
    overview: { spendText: '0.00', savedText: '0.00', budgetLabel: '预算', budgetText: '未设置', budgetCls: '', overspent: false },
    goal: { targetText: '0.00', savedText: '0.00', remainText: '0.00', progress: 0, hasTarget: false },
    // 消费日历 + 最近消费共用这一份当月账单
    calBills: [],
    recent: [],
    // 点日历某天弹出的当天明细
    showDay: false,
    dayLabel: '',
    dayList: [],
    // 快捷记账弹窗
    showQuick: false,
    quickCats: ['餐饮', '购物', '交通', '生活', '娱乐', '医疗', '其他'],
    quick: { amount: '', category: '餐饮', bill_date: '', note: '', submitting: false },
    // 目标设置弹窗
    showGoal: false,
    goalForm: { target: '', limit: '', submitting: false },
    // 精选攻略
    articles: [],
    loading: true
  },

  onLoad() {
    this.setData({ month: currentMonth(), monthText: parseInt(currentMonth().slice(5), 10) + '月' })
    this.loadArticles()
  },

  onShow() {
    // 每次回首页刷新个人数据（有 2 秒内存缓存，tab 来回切不会重复打接口）
    this.setData({ loggedIn: !!getApp().globalData.token })
    if (getApp().globalData.token) this.loadHomeData()
  },

  onPullDownRefresh() {
    wx.vibrateShort({ type: 'light' })
    const jobs = []
    if (getApp().globalData.token) jobs.push(this.loadHomeData(true))
    jobs.push(this.rotateArticles())
    Promise.all(jobs).finally(() => wx.stopPullDownRefresh())
  },

  // ---------- 个人数据：概览 + 目标 + 最近消费 ----------
  async loadHomeData(force = false) {
    try {
      const month = this.data.month || currentMonth()
      const [plan, bills] = await Promise.all([
        request('/checkin/plan', 'GET', {}, force),
        request('/bills?month=' + month, 'GET', {}, force)
      ])
      this._planCache = plan
      this._monthBills = bills || []
      this.setData({
        overview: this._overviewOf(plan),
        goal: this._goalOf(plan),
        calBills: this._monthBills,
        recent: this._recentOf(this._monthBills)
      })
    } catch (e) { /* 401 已由 request 统一处理；其余失败保持上次数值 */ }
  },

  _overviewOf(plan) {
    const spend = parseFloat(plan && plan.spend) || 0
    const saved = parseFloat(plan && plan.saved_amount) || 0
    const limit = parseFloat(plan && plan.spend_limit) || 0
    if (limit > 0) {
      const left = Math.round((limit - spend) * 100) / 100
      return {
        spendText: fmt(spend), savedText: fmt(saved),
        budgetLabel: left >= 0 ? '预算剩余' : '已超支',
        budgetText: fmt(Math.abs(left)),
        budgetCls: left >= 0 ? 'pos' : 'neg',
        overspent: left < 0
      }
    }
    return { spendText: fmt(spend), savedText: fmt(saved), budgetLabel: '预算', budgetText: '设置预算', budgetCls: 'set', overspent: false }
  },

  _goalOf(plan) {
    const target = parseFloat(plan && plan.target_amount) || 0
    const saved = parseFloat(plan && plan.saved_amount) || 0
    if (target <= 0) return { hasTarget: false, progress: 0, targetText: '0.00', savedText: '0.00', remainText: '0.00' }
    // 还差最低为 0；进度封顶 100%；「已省」不在目标区重复展示，上方实际节省是唯一口径
    const remain = Math.max(0, Math.round((target - saved) * 100) / 100)
    return {
      hasTarget: true,
      targetText: fmt(target), savedText: fmt(saved), remainText: fmt(remain),
      progress: Math.min(100, Math.round(saved / target * 1000) / 10)
    }
  },

  _recentOf(bills) {
    return (bills || []).slice(0, 4).map(b => ({
      id: b.id,
      amountText: fmt(b.amount),
      category: b.category || '其他',
      color: CAT_COLORS[b.category] || CAT_COLORS['其他'],
      day: String(b.bill_date || '').slice(5, 10),
      note: b.source || b.category || ''
    }))
  },

  goLogin() { wx.redirectTo({ url: '/pages/login/login' }) },

  // 概览卡上的预算入口：没设预算时点它直接开目标弹窗
  onBudgetTap() {
    if (this.data.overview.budgetCls === 'set') this.openGoal()
    else this.goBill()
  },

  // ---------- 消费日历 ----------
  onDayPick(e) {
    const d = e.detail || {}
    const date = d.date || ''
    const rows = (this._monthBills || []).filter(b => String(b.bill_date || '').slice(0, 10) === date)
    this.setData({
      showDay: true,
      dayLabel: date.slice(5).replace('-', '月') + '日',
      dayList: rows.map(b => ({
        id: b.id,
        amountText: fmt(b.amount),
        category: b.category || '其他',
        color: CAT_COLORS[b.category] || CAT_COLORS['其他'],
        note: b.source || b.category || ''
      }))
    })
  },

  closeDay() { this.setData({ showDay: false }) },

  // ---------- 快捷记一笔 ----------
  openQuick() {
    this.setData({
      showQuick: true,
      quick: { amount: '', category: '餐饮', bill_date: formatDate(new Date()), note: '', submitting: false }
    })
  },

  closeQuick() {
    if (this.data.quick.submitting) return // 提交中不允许关，避免误触丢表单
    this.setData({ showQuick: false })
  },

  onQuickInput(e) {
    const k = 'quick.' + e.currentTarget.dataset.field
    this.setData({ [k]: e.detail.value })
  },

  pickQuickCat(e) {
    this.setData({ 'quick.category': e.currentTarget.dataset.cat })
  },

  onQuickDate(e) {
    this.setData({ 'quick.bill_date': e.detail.value })
  },

  async submitQuick() {
    const q = this.data.quick
    if (q.submitting) return
    const value = parseFloat(q.amount)
    if (!(value > 0)) { wx.showToast({ title: '金额要大于 0', icon: 'none' }); return }
    if (value > 100000000) { wx.showToast({ title: '金额太大', icon: 'none' }); return }
    if (!q.bill_date) { wx.showToast({ title: '请选消费日期', icon: 'none' }); return }
    this.setData({ 'quick.submitting': true })
    try {
      await request('/bills', 'POST', {
        amount: Math.round(value * 100) / 100,
        category: q.category,
        source: (q.note || '').slice(0, 60),
        bill_date: q.bill_date
      })
      wx.showToast({ title: '已记一笔', icon: 'success' })
      this.setData({ showQuick: false })
      this.loadHomeData(true)
    } catch (e) {
      // 失败保留已填内容，允许改了重试
      this.setData({ 'quick.submitting': false })
    }
  },

  // ---------- 省钱目标 ----------
  openGoal() {
    const p = this._planCache || {}
    this.setData({
      showGoal: true,
      goalForm: {
        // 预填当前值，改目标不会顺手抹掉已设的支出上限
        target: p.target_amount ? String(p.target_amount) : '',
        limit: p.spend_limit ? String(p.spend_limit) : '',
        submitting: false
      }
    })
  },

  closeGoal() {
    if (this.data.goalForm.submitting) return
    this.setData({ showGoal: false })
  },

  onGoalInput(e) {
    const k = 'goalForm.' + e.currentTarget.dataset.field
    this.setData({ [k]: e.detail.value })
  },

  async submitGoal() {
    const f = this.data.goalForm
    if (f.submitting) return
    const target = parseFloat(f.target) || 0
    const limit = parseFloat(f.limit) || 0
    if (target < 0 || limit < 0) { wx.showToast({ title: '目标不能是负数', icon: 'none' }); return }
    if (target <= 0 && limit <= 0) { wx.showToast({ title: '至少填一个：省多少，或最多花多少', icon: 'none' }); return }
    this.setData({ 'goalForm.submitting': true })
    try {
      const plan = await request('/checkin/plan', 'POST', {
        target_amount: Math.round(target * 100) / 100,
        spend_limit: Math.round(limit * 100) / 100
      })
      this._planCache = plan
      wx.showToast({ title: '目标已保存', icon: 'success' })
      this.setData({ showGoal: false })
      this.loadHomeData(true)
    } catch (e) {
      this.setData({ 'goalForm.submitting': false })
    }
  },

  // ---------- 跳转 ----------
  goBill() { wx.switchTab({ url: '/pages/bill/bill' }) },

  goBillFocus() {
    // switchTab 带不了 query，深链定位走 globalData，账单页 onShow 消费
    getApp().globalData.pendingBillFocus = 'report'
    wx.switchTab({ url: '/pages/bill/bill' })
  },

  goPrice() { wx.navigateTo({ url: '/pages/price/price' }) },

  goArticles() { wx.navigateTo({ url: '/pages/articles/articles' }) },

  // ---------- 精选攻略：下拉轮换，完整搜索/筛选在独立攻略页 ----------
  async loadArticles(force = false) {
    this.setData({ loading: true })
    try {
      const data = await request('/articles', 'GET', {}, force)
      // cover 存的是 /static/ 相对路径，<image> 要绝对地址
      this._all = (data || []).map(a => Object.assign({}, a, { coverUrl: fullUrl(a.cover) }))
      this._viewed = {} // 已展示 id 集合（轮换用）
      this._cursor = 0
      this.setData({ articles: this.pickNext(), loading: false })
    } catch (e) {
      this.setData({ loading: false, articles: [] })
      console.error(e)
    }
  },

  async rotateArticles() {
    if (!this._all || !this._all.length) return this.loadArticles()
    this.setData({ articles: this.pickNext() })
  },

  // 从全量中取下一批未看过的 8 条；全部看完则循环
  pickNext() {
    this._viewed = this._viewed || {}
    this._cursor = this._cursor || 0
    const all = this._all || []
    let unseen = all.filter(a => !this._viewed[a.id])
    if (unseen.length === 0) {
      this._viewed = {}
      unseen = all
    }
    const batch = []
    let picked = 0
    const start = this._cursor % Math.max(all.length, 1)
    for (let i = 0; picked < PAGE && i < all.length; i++) {
      const item = all[(start + i) % all.length]
      if (!this._viewed[item.id]) {
        batch.push(item)
        this._viewed[item.id] = true
        picked++
      }
    }
    this._cursor += picked
    return batch
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + e.currentTarget.dataset.id })
  },

  goCreate() {
    wx.navigateTo({ url: '/pages/articleCreate/articleCreate' })
  },

  // 问 AI：跳 AI 助手，省得用户再打一遍字
  goAsk() {
    getApp().globalData.pendingAsk = {
      agent: 'coupon',
      question: '最近有什么值得薅的羊毛和省钱攻略？',
    }
    wx.switchTab({ url: '/pages/assistant/assistant' })
  }
})
