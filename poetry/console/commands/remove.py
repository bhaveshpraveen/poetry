from cleo import argument
from cleo import option

from .installer_command import InstallerCommand


class RemoveCommand(InstallerCommand):

    name = "remove"
    description = "Removes a package from the project dependencies."

    arguments = [argument("packages", "The packages to remove.", multiple=True)]
    options = [
        option("dev", "D", "Remove a package from the development dependencies."),
        option(
            "dry-run",
            None,
            "Output the operations but do not execute anything "
            "(implicitly enables --verbose).",
        ),
    ]

    help = """The <info>remove</info> command removes a package from the current
list of installed packages

<info>poetry remove</info>"""

    loggers = ["poetry.repositories.pypi_repository", "poetry.inspection.info"]

    def handle(self):
        packages = self.argument("packages")
        is_dev = self.option("dev")

        original_content = self.poetry.file.read()
        content = self.poetry.file.read()
        poetry_content = content["tool"]["poetry"]
        dev_dep = {key: val for key, val in poetry_content["dev-dependencies"].items()}
        main_dep = {key: val for key, val in poetry_content["dependencies"].items()}

        dev_dep_to_remove = {}
        main_dep_to_remove = {}

        # dev-dependencies section
        for name in packages:
            for key in dev_dep:
                if key.lower() == name.lower():
                    dev_dep_to_remove[key] = dev_dep[key]

        # dependencies section
        if not is_dev:
            for name in packages:
                for key in main_dep:
                    # present in both dev and main dependency
                    if key.lower() == name.lower() and dev_dep_to_remove.get(key):
                        question = self.create_question(
                            "Package {} present in both dependencies and dev-dependencies."
                            "Please specify the section to remove the package from ".format(
                                name
                            ),
                            type="choice",
                            choices=["dev-dependencies", "dependencies", "both"],
                        )
                        section = self.ask(question)
                        if section == "dependencies":
                            del dev_dep_to_remove[key]
                            main_dep_to_remove[key] = main_dep[key]
                        if section == "both":
                            main_dep_to_remove[key] = main_dep[key]

                    elif key.lower() == name.lower():
                        main_dep_to_remove[key] = main_dep[key]

        # check if any of the packages were not found
        for name in packages:
            all_deps = list(dev_dep_to_remove) + list(main_dep_to_remove)
            if name.lower() not in [dep.lower() for dep in all_deps]:
                self.line_error("Package {} not found".format(name))
                return

        # delete from pyproject.toml file
        for key in dev_dep_to_remove:
            del poetry_content["dev-dependencies"][key]
        for key in main_dep_to_remove:
            del poetry_content["dependencies"][key]

        # todo: if a package is in both the sections, which version to use?
        requirements = dev_dep.copy()
        requirements.update(main_dep_to_remove)

        # Write the new content back
        self.poetry.file.write(content)

        # Update packages
        self.reset_poetry()

        self._installer.use_executor(
            self.poetry.config.get("experimental.new-installer", False)
        )

        self._installer.dry_run(self.option("dry-run"))
        self._installer.verbose(self._io.is_verbose())
        self._installer.update(True)
        self._installer.whitelist(requirements)

        try:
            status = self._installer.run()
        except Exception:
            self.poetry.file.write(original_content)

            raise

        if status != 0 or self.option("dry-run"):
            # Revert changes
            if not self.option("dry-run"):
                self.line_error(
                    "\n"
                    "Removal failed, reverting pyproject.toml "
                    "to its original content."
                )

            self.poetry.file.write(original_content)

        return status
