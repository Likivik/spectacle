
with den.aspects; --> doesn't work, error: _ -> undefined
```
    includes = with den.aspects; [
      core._                  # ._ --> Includes every sub-aspect (1st level only)
      desktop.common-core._
      desktop.common-extra._
      desktop.desktopManagers.kde
      desktop.apps._
    ];
```
but this does:
```
    includes = [
      den.aspects.core._                  # ._ --> Includes every sub-aspect (1st level only)
      den.aspects.desktop.common-core._
      den.aspects.desktop.common-extra._
      den.aspects.desktop.desktopManagers.kde
      den.aspects.desktop.apps._
    ];
```