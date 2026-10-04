# Read by every kernel started from this environment, the container's and the
# image check's alike. It sits in the venv's etc/ipython: IPython looks there,
# not in Jupyter's config path.
c = get_config()  # noqa: F821

c.IPKernelApp.extensions = ["not_a_notebook_display"]
