# Get involved

Our goals:

- Theoretical Quality: Expert driven features with research and open case studies.
- Feature Quality: Broadly useful and extendable features with good documentation and some testing.

Less abstractly, there are a good number of **coding** and **non-coding** tasks to chip in with:

## Give feedback

Read through this document, let us know what you think, share.
Feedback gladly received as an [issue](https://github.com/arup-group/pam/issues), on [slack](https://join.slack.com/share/I011QU6NN9J/3jAlIBVEbvNln55kGvtZv6ML/zt-dih8pklw-nOPgRzbL3SKj5coH9xemFA) or you can email fred.shone@arup.com.

## Literature review

We still need validation of the overall approach.
Much of the methodology (detailed in this document) is based on what can pragmatically be done, not what theoretically should be done.
We'd appreciate links to relevant papers.
Or even better we'd love a lit review - we'll add it to this document.

## Research

We need help with designing useful features, applying them to real problems.
As part of this we need:

### Evidence and data for validation

We know, for example, that many people have removed certain activities from their daily plans, such as to school or university.
But we don't know how many.
We'd like help finding and eventually applying **validation data** such as recent [change in mobility](https://www.google.com/covid19/mobility/).

### Evidence for new features

We currently support the following activity plan modifications:

- probabilistic removal of all activities, i.e., full quarantine or isolation
- probabilistic removal of specific activities, i.e., education
- automatic extension of other (typically staying at home) activities

But we'd like help to **find evidence** for other modifications that we think are occurring:

- changing duration of an activity
- moving activity closer to home, i.e., shopping trips
- changing travel choice, i.e., mode
- moving home location (i.e., national and local emigration)
- household shared activities/no longer shared activities, such as leisure
- defining key workers

### Evidence for technical methodology

Modifying a plan to remove an activity can cascade into other changes.
In the case of people with complex chains of activities, the removal of a single activity requires adjustments to the remainder.
Do people leave later of earlier if they have more time for example?
The methods for this logic is in `pam.core.People`.

## Develop

### Setting up a development environment

If you have followed the recommended installation instructions, all libraries required for development and quality assurance will already be installed.
If installing directly with pip, you can install these libraries using the `dev` option, i.e., `pip install -e ./pam[dev]`

If you plan to make changes to the code then please make regular use of the following tools to verify the codebase while you work:

- `pre-commit`: run `pre-commit install` in your command line to load inbuilt checks that will run every time you commit your changes.
The checks are: 1. check no large files have been staged, 2. lint python files for major errors, 3. format python files to conform with the [pep8 standard](https://peps.python.org/pep-0008/).
You can also run these checks yourself at any time to ensure staged changes are clean by simple calling `pre-commit`.
- `pytest` - run the unit test suite, check test coverage, and test that the example notebooks successfully run.

### Contributing

To find beginner-friendly existing bugs and feature requests you may like to have a crack at, take a look [here](https://github.com/arup-group/pam/contribute).

We maintain a backlog of [issues](https://github.com/arup-group/pam/issues), please in touch if you would like to contribute - or raise your own issue.

We need help to **go faster**. We expect to deal with populations in the tens of millions.
We would like help with profiling and implementing parallel compute.

If you want to dive deeper into development, we recommend you get in touch with us by joining our [slack](https://join.slack.com/share/I011QU6NN9J/3jAlIBVEbvNln55kGvtZv6ML/zt-dih8pklw-nOPgRzbL3SKj5coH9xemFA) channel.

## Use cases
We will share open and dummy data where available, we would love people to do some experiments and develop some viz and validation pipelines.
Any example notebooks can be added to the [example notebooks](https://github.com/arup-group/pam/tree/master/examples).