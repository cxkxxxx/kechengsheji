// 社区页逻辑：广场信息流（每屏固定 8 条，下拉刷新轮换展示未看过的）
const { request } = require('../../utils/request')

const PAGE = 8

// 后端给的是 ISO 时间串，列表只需要「月-日 时:分」
function briefTime(v) {
  const s = String(v || '')
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  if (!m) return s.slice(0, 10)
  const now = new Date()
  const sameYear = +m[1] === now.getFullYear()
  return (sameYear ? '' : m[1] + '年') + (+m[2]) + '月' + (+m[3]) + '日 ' + m[4] + ':' + m[5]
}

// tags 存的是逗号分隔字符串
function briefTags(v) {
  if (!v) return []
  return String(v).split(/[,，]/).map(t => t.trim()).filter(Boolean).slice(0, 3)
}

function decorate(p) {
  return Object.assign({}, p, { timeText: briefTime(p.created_at), tagList: briefTags(p.tags) })
}

Page({
  data: { posts: [], refreshing: false, loading: true },

  onLoad() { this.loadPosts() },
  onShow() { this.loadPosts() },

  // 初始/返回：加载全量并显示前 8 条（保留已轮换的状态）
  async loadPosts(force = false) {
    try {
      const data = await request('/posts', 'GET', {}, force)
      if (Array.isArray(data) && data.length) {
        this._all = data
        if (!this._viewed) { this._viewed = {}; this._cursor = 0 }
        // 仅首次/无数据时填充 8 条
        if (this.data.posts.length === 0) {
          this.setData({ posts: this.pickNext().map(decorate), loading: false })
        } else {
          this.setData({ loading: false })
        }
      } else if (!this._all) {
        this._all = []
        this._viewed = {}
        this._cursor = 0
        this.setData({ posts: [], loading: false })
      } else {
        this.setData({ loading: false })
      }
    } catch (e) {
      this.setData({ loading: false })
      console.error(e)
    }
  },

  // 下拉刷新：轮换下一批未看过的 8 条
  onRefresherRefresh() {
    this.setData({ refreshing: true })
    wx.vibrateShort({ type: 'light' })
    setTimeout(() => {
      if (this._all && this._all.length) {
        this.setData({ posts: this.pickNext().map(decorate) })
      } else {
        this.loadPosts()
      }
      this.setData({ refreshing: false })
    }, 500)
  },

  pickNext() {
    const all = this._all || []
    let unseen = all.filter(p => !this._viewed[p.id])
    if (unseen.length === 0) { this._viewed = {}; unseen = all }
    const batch = []
    const start = this._cursor % Math.max(all.length, 1)
    let picked = 0
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

  goPostDetail(e) {
    wx.navigateTo({ url: '/pages/postDetail/postDetail?id=' + e.currentTarget.dataset.id })
  },

  // 点赞/取消点赞（catchtap 阻止冒泡）
  async likePost(e) {
    const id = e.currentTarget.dataset.id
    try {
      const res = await request('/posts/' + id + '/like', 'POST')
      this._all = (this._all || []).map(p => {
        if (p.id == id) { p.likes = res.likes; p.liked = res.liked }
        return p
      })
      this.setData({ posts: this.data.posts.map(p => {
        if (p.id == id) { p.likes = res.likes; p.liked = res.liked }
        return p
      }) })
    } catch (err) { console.error(err) }
  },

  goCreatePost() {
    wx.navigateTo({ url: '/pages/postCreate/postCreate' })
  }
})
