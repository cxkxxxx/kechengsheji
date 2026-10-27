// 执行计划页：无 id = 历史列表；带 id = 计划详情（勾步骤、记实买、确认实际节省）
const { request } = require('../../utils/request')
const { formatMoney } = require('../../utils/util')

Page({
  data: {
    planId: 0,
    // 列表态
    list: [],
    loadingList: true,
    // 详情态
    detail: null,          // {id, title, article_id, plan, est_saving, actual_saving, status}
    steps: [],
    shopping: [],
    savingForm: { amount: '', note: '' },
    busy: false,
  },

  onLoad(options) {
    if (options && options.id) {
      this.planId = parseInt(options.id)
      this.setData({ planId: this.planId })
      this.loadDetail()
    } else {
      this.loadList()
    }
  },

  onShow() {
    // 从攻略页/比价页回来时刷新进度
    if (this.planId && this.data.detail) this.loadDetail(true)
  },

  // ---------- 列表态 ----------
  async loadList() {
    try {
      const d = await request('/ai/exec-plans', 'GET', {}, true)
      this.setData({
        list: (d.items || []).map(r => Object.assign({}, r, {
          progress: r.steps_total ? Math.round(r.steps_done / r.steps_total * 100) : 0,
          estText: r.est_saving > 0 ? formatMoney(r.est_saving) : '',
          actualText: r.actual_saving > 0 ? formatMoney(r.actual_saving) : ''
        })),
        loadingList: false
      })
    } catch (e) {
      this.setData({ loadingList: false })
    }
  },

  openPlan(e) {
    wx.navigateTo({ url: '/pages/plan/plan?id=' + e.currentTarget.dataset.id })
  },

  goHome() {
    wx.switchTab({ url: '/pages/index/index' })
  },

  // ---------- 详情态 ----------
  async loadDetail(quiet) {
    if (!quiet) this.setData({ loadingList: false })
    try {
      const d = await request('/ai/exec-plans/' + this.planId, 'GET', {}, true)
      const plan = d.plan || {}
      this.setData({
        detail: d,
        steps: plan.steps || [],
        shopping: (plan.shopping || []).map(s => Object.assign({}, s, {
          estText: s.est_price > 0 ? formatMoney(s.est_price) : '',
          actualText: s.actual > 0 ? formatMoney(s.actual) : ''
        })),
        prep: plan.prep || [],
        cautions: plan.cautions || [],
        budgetAdvice: plan.budget_advice || '',
        keywords: plan.product_keywords || [],
        estText: d.est_saving > 0 ? formatMoney(d.est_saving) : '',
        actualText: d.actual_saving > 0 ? formatMoney(d.actual_saving) : ''
      })
    } catch (e) { console.error(e) }
  },

  async toggleStep(e) {
    const i = e.currentTarget.dataset.i
    const key = 'steps[' + i + '].done'
    this.setData({ [key]: !this.data.steps[i].done })
    this._savePlan()
  },

  onActualInput(e) {
    const i = e.currentTarget.dataset.i
    this.setData({ ['shopping[' + i + '].actualRaw']: e.detail.value })
  },

  toggleBought(e) {
    const i = e.currentTarget.dataset.i
    this.setData({ ['shopping[' + i + '].bought']: !this.data.shopping[i].bought })
    this._savePlan()
  },

  // 步骤/清单的编辑整包保存；金额失焦时一并带上
  async _savePlan() {
    if (this._saving) return
    this._saving = true
    try {
      const shopping = this.data.shopping.map(s => Object.assign({}, s, {
        actual: parseFloat(s.actualRaw || s.actual) || 0
      }))
      await request('/ai/exec-plans/' + this.planId, 'PUT', {
        steps: this.data.steps, shopping
      })
      // 本地同步一遍，别等刷新
      this.setData({ shopping })
    } catch (e) { console.error(e) }
    finally { setTimeout(() => { this._saving = false }, 300) }
  },

  onActualBlur() { this._savePlan() },

  // ---------- 实际节省：只收用户确认的金额，写 checkins（AI 预计不算数） ----------
  onSavingInput(e) {
    this.setData({ ['savingForm.' + e.currentTarget.dataset.field]: e.detail.value })
  },

  async confirmSaving() {
    if (this.data.busy) return
    const v = parseFloat(this.data.savingForm.amount)
    if (!(v > 0)) {
      wx.showToast({ title: '填写实际省下的金额', icon: 'none' }); return
    }
    this.setData({ busy: true })
    try {
      await request('/ai/exec-plans/' + this.planId + '/confirm-saving', 'POST', {
        amount: Math.round(v * 100) / 100,
        note: this.data.savingForm.note || ''
      })
      this.setData({ busy: false, savingForm: { amount: '', note: '' } })
      wx.showToast({ title: '已记入省钱成果', icon: 'success' })
      this.loadDetail(true)
    } catch (e) {
      this.setData({ busy: false })
    }
  },

  // ---------- 比价关联：清单商品拿去比价（有真实报价才展示，不编价格） ----------
  goPrice(e) {
    const kw = e.currentTarget.dataset.kw
    wx.navigateTo({ url: '/pages/price/price?q=' + encodeURIComponent(kw) })
  },

  // ---------- 分享经验：带草稿去发帖页，正式发布仍由用户点发布 ----------
  sharePost() {
    const d = this.data.detail
    if (!d) return
    const done = this.data.steps.filter(s => s.done).length
    const app = getApp()
    app.globalData.pendingPost = {
      title: '照攻略《' + d.title + '》实践完了',
      content: '按这篇攻略执行了 ' + this.data.steps.length + ' 步，完成 ' + done
        + ' 步。' + (this.data.actualText ? '实际省了 ' + this.data.actualText + ' 元。' : '')
        + '说说过程和踩的坑：',
      tags: '执行报告'
    }
    wx.navigateTo({ url: '/pages/postCreate/postCreate' })
  },

  goArticle() {
    const d = this.data.detail
    if (d && d.article_id) {
      wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + d.article_id })
    }
  },
})
