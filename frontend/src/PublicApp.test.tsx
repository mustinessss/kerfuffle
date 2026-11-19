import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import PublicApp from "./PublicApp";

afterEach(cleanup);

describe("public frontend routes", () => {
  it("renders registrar code access without administrative navigation", () => {
    window.history.pushState({}, "", "/register");
    render(<PublicApp />);

    expect(screen.getByRole("heading", { name: /Регистрация участников/ })).toBeTruthy();
    expect(screen.getByLabelText("Код регистратора")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Рабочее пространство|Рейтинг|Войти/ })).toBeNull();
  });

  it("renders station-holder access without administrative navigation", () => {
    window.history.pushState({}, "", "/score");
    render(<PublicApp />);

    expect(screen.getByLabelText("Код доступа площадки")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Рабочее пространство|Рейтинг|Войти/ })).toBeNull();
  });
});
