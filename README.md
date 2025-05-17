![Banner](.github/assets/banner.png)

> [!IMPORTANT]
>
> Discord RAM in early-alpha development stage. We don't recommend you to try use it, but you can experiment. :) ([Contributing])

# Discord RAM

> ram [/ræm/] – a framework (or frame) from Sweden.

A static-typed, fully asynchronous and flexible Discord API framework for Python 3.

# Resources
- [Examples](./examples/)

# Modules

## [ram](./src/ram)
A high-level interface built on top of [ramx](#ramx).

## [ramx](./src/ramx)

A lightweight microframework for interacting with the Discord API.

# Project Goal

The primary motivation behind this project is the absence of existing libraries that fully meet my specific needs. This library aims to fill that gap by offering a solution focused entirely on (de)serialization and validation using [`msgspec`].

## Why [`msgspec`]?

- Convenient
- Pragmatic
- Fast

This project does not aspire to compete with larger libraries.

# Issues

Any feedback is welcome! If you encounter any bugs or have suggestions, feel free to submit them on our [issues page](https://github.com/stefanlight8/discord-ram/issues).

You can also help implement your idea by submitting a pull request, but please check the [Contributing] section first.

# Contributing

Please familiarize yourself with our [contributing guidelines](./CONTRIBUTING.md) before contributing.

We recommend:
- We use [uv](https://astral.sh/uv) and recommend using it too.

# Inspiration

### ❤️ [hikari](https://github.com/hikari-py/hikari)

A Discord API wrapper for Python and asyncio, built on good intentions.

[Contributing]: #contributing
[`msgspec`]: https://pypi.org/project/msgspec