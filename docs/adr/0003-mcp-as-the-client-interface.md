# 0003. Model Context Protocol as the client interface

Date: 2026-07-31

## Status

Accepted

## Context

The motivating frustration is that memory today is trapped inside individual assistants.
Each provider's memory works only with that provider's models, in that provider's cloud.
Building yet another chat application with its own private memory would reproduce the problem
at smaller scale.

Two requirements are in tension. The system must work with commercial assistants when
connected, because that is where the conversations actually happen. It must also work with
no external network at all, against locally served models.

## Decision

Memory is exposed as a Model Context Protocol server. Clients — commercial assistants,
local chat interfaces, agent runtimes, and this project's own web UI — are consumers of that
interface rather than owners of the memory.

MCP is a protocol, not a hosted service. The server runs locally over stdio or a LAN socket
and is indifferent to whether the host has internet access, in the same way HTTP works on a
disconnected network. The identical server therefore serves both postures: connected, it
lets commercial assistants read and write shared memory; disconnected, local clients use it
unchanged.

## Consequences

Integration cost per client drops to zero for anything that speaks MCP, which is the main
benefit and the reason memory becomes portable across providers.

The web UI is demoted to one client among several. It cannot hold private state or take
shortcuts around the interface, which is a constraint but keeps the boundary honest.

Tool design becomes a public API design problem. Tool names, arguments, and returned shapes
are consumed by models rather than programmers, and changing them breaks callers. This
warrants versioning discipline earlier than a private interface would.

Sending memory to a commercial assistant means that content leaves the machine. The
protocol makes this possible but does not make it safe, so what is exposed to remote clients
must be scoped deliberately rather than by default.

This choice also bets on MCP remaining a relevant standard. If it is displaced, the server
becomes an adapter and the graph beneath it is unaffected — the blast radius is one component.

## Alternatives considered

**A plain REST API.** Universal and simple, but every client would need a bespoke
integration, which is precisely the cost MCP removes.

**A monolithic chat application with built-in memory.** Fastest path to a usable product,
rejected because it recreates the walled garden this project exists to escape.

**Provider-specific plugins.** Best possible experience per assistant, at the cost of
maintaining one integration per provider forever.
