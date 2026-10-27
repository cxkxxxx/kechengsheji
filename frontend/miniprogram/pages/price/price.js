// 比价页：/price/compare 后端早就写好了（AI 工具走的是同一套编排），
// 但前端一直没有入口，比价只能藏在 AI 对话里。这里做成独立一页，
// 输入商品名或粘整段分享文案，直接出各渠道到手价对比。
const { request } = require('../../utils/request')
const { formatMoney } = require('../../utils/util')

const CAT_COLORS = {
  '餐饮': '#60768C', '购物': '#8797A7', '交通': '#A6B1BC',
  '生活': '#73897F', '娱乐': '#9B8974', '医疗': '#778A9A', '其他': '#C2C9D0'
}

Page({
  data: {
    kw: '',
    loading: false,
    searched: false,
    res: null,
    items: [],
    history: []
  },

  onLoad(options) {
    // 上次搜过的商品，省得反复打字
    this.setData({ history: wx.getStorageSync('price_history') || [] })
    // 执行计划/其它页面带关键词跳进来时直接搜
    if (options && options.q) {
      this.setData({ kw: decodeURIComponent(options.q) })
      this.search()
    }
  },

  onInput(e) { this.setData({ kw: e.detail.value }) },

  tapHistory(e) {
    this.setData({ kw: e.currentTarget.dataset.kw })
    this.search()
  },

  clearAll() {
    wx.removeStorageSync('price_history')
    this.setData({ history: [] })
  },

  async search() {
    const kw = (this.data.kw || '').trim()
    if (!kw) {
      wx.showToast({ title: '先输入商品名或粘一条链接', icon: 'none' })
      return
    }
    if (this.data.loading) return
    this.setData({ loading: true })
    try {
      // 用户经常直接粘整段分享文案，链接里带 http 就交给后端 link 参数去解析平台
      const isLink = /https?:\/\//.test(kw)
      const url = '/price/compare?' + (isLink ? 'link=' : 'keyword=') + encodeURIComponent(kw)
      const d = await request(url, 'GET')
      const items = (d.items || []).map(it => Object.assign({}, it, {
        priceText: formatMoney(it.final_price || it.price),
        couponText: it.coupon_amount ? '券 ' + formatMoney(it.coupon_amount) + ' 元' : '',
        color: CAT_COLORS[it.platform] || '#8797A7'
      }))
      const lowest = items.length ? items[0] : null
      this.setData({
        loading: false,
        searched: true,
        items,
        res: Object.assign({}, d, {
          lowestText: lowest ? lowest.priceText : '',
          spreadText: d.spread ? formatMoney(d.spread) + ' 元' : '',
          histLowText: d.hist_low ? formatMoney(d.hist_low) + ' 元' : ''
        })
      })
      this._remember(kw)
    } catch (e) {
      this.setData({ loading: false, searched: true, items: [], res: null })
      wx.showToast({ title: e.message || '查询失败', icon: 'none' })
    }
  },

  _remember(kw) {
    const h = (this.data.history || []).filter(x => x !== kw)
    h.unshift(kw)
    const cut = h.slice(0, 8)
    wx.setStorageSync('price_history', cut)
    this.setData({ history: cut })
  },

  // 微信小程序打不开外部网址，只能复制链接让用户去浏览器粘贴
  copyUrl(e) {
    const url = e.currentTarget.dataset.url
    if (!url) return
    wx.setClipboardData({
      data: url,
      success() { wx.showToast({ title: '链接已复制，到浏览器打开', icon: 'none' }) }
    })
  },

  goAssistant() {
    wx.switchTab({ url: '/pages/assistant/assistant' })
  }
})
