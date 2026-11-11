import { defineAppSetup } from '@slidev/types'

// Workaround for a Slidev + vue-router 5 base-path bug.
//
// When the deck is built with a non-root --base (e.g. /UnpackThePCAP/<deck>/),
// Slidev's getSlidePath() returns paths that already include BASE_URL, then
// hands them to router.push(). vue-router 5 prepends the base *again*, so
// pressing arrow keys navigates to a doubled URL like
//   /UnpackThePCAP/<deck>/UnpackThePCAP/<deck>/2
// which matches nothing and breaks navigation.
//
// This guard detects a navigation target that still carries the base prefix
// and rewrites it to the correct base-relative path before the router resolves
// it. Deep links and refreshes (which arrive already base-stripped) pass
// through untouched.
export default defineAppSetup(({ router }) => {
  // BASE_URL is like "/UnpackThePCAP/<deck>/"; drop the trailing slash so we
  // can match "<base>/<rest>" without tripping on the root path itself.
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  if (!base)
    return

  router.beforeEach((to) => {
    if (to.path !== base && to.path.startsWith(`${base}/`)) {
      return {
        path: to.path.slice(base.length),
        query: to.query,
        hash: to.hash,
        replace: true,
      }
    }
    return true
  })
})
