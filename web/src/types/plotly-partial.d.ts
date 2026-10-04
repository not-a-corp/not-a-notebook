// plotly.js types its full entry point only; the prebuilt partial bundles are
// the same API with fewer trace types registered.
declare module "plotly.js/dist/plotly-cartesian.min.js" {
  import Plotly from "plotly.js";
  export default Plotly;
}
