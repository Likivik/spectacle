## Big patterns:

1. Provides

2. Quirks + Pipe.collect

---

## Single purpose:

1. den.schema.<kind>.includes
    Anything added here is automatically applied to every entity of that kind (e.g., all hosts or all users or all hm-hosts, hjem, maid, I think there are others, custom ones can also be created I think).

2. den.batteries.mutual-provider
    Basically provides.to-users and provides.to-hosts everywhere.





---

Don't understand:

1. excludes
2. policy.route
3. den.policies
   1. policy.resolve
   2. policy.resolve.to

---

Notes:

Policy Activation: Policies are only active if they are included in an includes list (either in an aspect, a schema, or den.default)